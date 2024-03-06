import os
import pathlib
import pickle
import subprocess
import tempfile

import requests
from dagster import (
    AssetExecutionContext,
    AssetSelection,
    Definitions,
    DynamicPartitionsDefinition,
    EnvVar,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    asset,
    define_asset_job,
    sensor,
)
from dagster_openai import OpenAIResource
from filelock import FileLock
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
from langchain.docstore.document import Document
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter
from langchain.vectorstores.faiss import FAISS
from langchain_community.llms import OpenAI

docs_partitions_def = DynamicPartitionsDefinition(name="docs")

DOCS_DIRECTORY = "./source_docs/"
SEARCH_INDEX_FILE = "search_index.pickle"


@asset
def source_docs():
    for url, doc in list(get_github_docs("dagster-io", "dagster")):
        filename = f"{DOCS_DIRECTORY}{url}"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "wb") as f:
            pickle.dump(doc, f)


@asset(compute_kind="OpenAI", partitions_def=docs_partitions_def)
def search_index(context: AssetExecutionContext, openai: OpenAIResource):
    filename = f"{DOCS_DIRECTORY}{context.partition_key}"
    with open(filename, "rb") as f:
        source = pickle.load(f)

    source_chunks = []
    splitter = CharacterTextSplitter(separator=" ", chunk_size=1024, chunk_overlap=0)
    for chunk in splitter.split_text(source.page_content):
        source_chunks.append(Document(page_content=chunk, metadata=source.metadata))

    with openai.get_client(context) as client:
        search_index = FAISS.from_documents(
            source_chunks, OpenAIEmbeddings(client=client.embeddings)
        )

    with FileLock(SEARCH_INDEX_FILE):
        if os.path.getsize(SEARCH_INDEX_FILE) > 0:
            with open(SEARCH_INDEX_FILE, "rb") as f:
                serialized_search_index = pickle.load(f)
            cached_search_index = FAISS.deserialize_from_bytes(
                serialized_search_index, OpenAIEmbeddings()
            )
            search_index.merge_from(cached_search_index)

        with open(SEARCH_INDEX_FILE, "wb") as f:
            pickle.dump(search_index.serialize_to_bytes(), f)


@asset(compute_kind="OpenAI")
def completion(context: AssetExecutionContext, openai: OpenAIResource):
    question = "What can I use Dagster for?"
    with open(SEARCH_INDEX_FILE, "rb") as f:
        serialized_search_index = pickle.load(f)
    search_index = FAISS.deserialize_from_bytes(serialized_search_index, OpenAIEmbeddings())
    with openai.get_client(context) as client:
        chain = load_qa_with_sources_chain(OpenAI(client=client.completions, temperature=0))
        context.log.info(
            chain(
                {
                    "input_documents": search_index.similarity_search(question, k=4),
                    "question": question,
                },
                return_only_outputs=True,
            )["output_text"]
        )


def get_wiki_data(title, first_paragraph_only):
    url = f"https://en.wikipedia.org/w/api.php?format=json&action=query&prop=extracts&explaintext=1&titles={title}"
    if first_paragraph_only:
        url += "&exintro=1"
    data = requests.get(url).json()
    return Document(
        page_content=next(iter(data["query"]["pages"].values()))["extract"],
        metadata={"source": f"https://en.wikipedia.org/wiki/{title}"},
    )


def get_github_docs(repo_owner, repo_name):
    with tempfile.TemporaryDirectory() as d:
        subprocess.check_call(
            f"git clone --depth 1 https://github.com/{repo_owner}/{repo_name}.git .",
            cwd=d,
            shell=True,
        )
        git_sha = (
            subprocess.check_output("git rev-parse HEAD", shell=True, cwd=d).decode("utf-8").strip()
        )
        repo_path = pathlib.Path(d)
        markdown_files = list(repo_path.glob("*/*.md")) + list(repo_path.glob("*/*.mdx"))
        for index, markdown_file in enumerate(markdown_files):
            with open(markdown_file, "r") as f:
                relative_path = markdown_file.relative_to(repo_path)
                github_url = (
                    f"https://github.com/{repo_owner}/{repo_name}/blob/{git_sha}/{relative_path}"
                )
                yield (
                    github_url.replace("/", "_"),
                    Document(page_content=f.read(), metadata={"source": github_url}),
                )


search_index_job = define_asset_job(
    "search_index_job", AssetSelection.keys("search_index"), partitions_def=docs_partitions_def
)


@sensor(job=search_index_job)
def docs_sensor(context: SensorEvaluationContext):
    new_docs = [
        doc_filename
        for doc_filename in os.listdir(DOCS_DIRECTORY)
        if not docs_partitions_def.has_partition_key(
            doc_filename, dynamic_partitions_store=context.instance
        )
    ]

    return SensorResult(
        run_requests=[RunRequest(partition_key=doc_filename) for doc_filename in new_docs],
        dynamic_partitions_requests=[docs_partitions_def.build_add_request(new_docs)],
    )


defs = Definitions(
    assets=[source_docs, search_index, completion],
    jobs=[search_index_job],
    resources={
        "openai": OpenAIResource(api_key=EnvVar("OPENAI_API_KEY")),
    },
    sensors=[docs_sensor],
)
