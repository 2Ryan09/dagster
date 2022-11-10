import wandb

from dagster import AssetIn, OpExecutionContext, asset

MODEL_NAME = "my_model"


@asset(
    name=MODEL_NAME,
    compute_kind="Python",
    io_manager_key="wandb_artifacts_manager",
)
def write_model() -> wandb.sdk.wandb_artifacts.Artifact:
    """Write your model.

    Here, we have we're creating a very simple Artifact with the integration.

    In a real scenario this would be more complex.

    Returns:
        wandb.Artifact: Our model
    """
    return wandb.Artifact(MODEL_NAME, "model")


@asset(
    compute_kind="Python",
    name="registered-model",
    ins={
        "artifact": AssetIn(
            asset_key=MODEL_NAME,
            input_manager_key="wandb_artifacts_manager",
        )
    },
    output_required=False,
    config_schema={"model_registry": str},
)
def promote_best_model_to_production(
    context: OpExecutionContext, artifact: wandb.apis.public.Artifact
):
    """Example that links a model stored in a W&B Artifact to the Model Registry.

    Args:
        context (OpExecutionContext): Dagster execution context
        artifact (wandb.apis.public.Artifact): Downloaded Artifact object
    """
    # In a real scenario you would evaluate model performance
    performance_is_better = True  # for simplicity we always promote the new model
    if performance_is_better:
        model_registry = context.op_config["model_registry"]
        # promote the model to production
        artifact.link(target_path=model_registry, aliases="production")
