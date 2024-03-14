import pytest
from dagster import AssetKey, AssetMaterialization, JsonMetadataValue, TableColumn, TableSchema
from dagster._core.definitions.metadata import (
    TableMetadataEntries,
)
from dagster._core.definitions.metadata.table import AssetColumnDep, TableColumnLineages
from dagster._core.errors import DagsterInvalidMetadata


def test_column_schema():
    column_schema = TableSchema(columns=[TableColumn("foo", "str")])
    table_metadata_entries = TableMetadataEntries(column_schema=column_schema)

    dict_table_metadata_entries = dict(table_metadata_entries)
    assert dict_table_metadata_entries == {"dagster/column_schema": column_schema}
    assert isinstance(dict_table_metadata_entries["dagster/column_schema"], TableSchema)
    AssetMaterialization(asset_key="a", metadata=dict_table_metadata_entries)

    splat_table_metadata_entries = {**table_metadata_entries}
    assert splat_table_metadata_entries == {"dagster/column_schema": column_schema}
    assert isinstance(splat_table_metadata_entries["dagster/column_schema"], TableSchema)
    AssetMaterialization(asset_key="a", metadata=splat_table_metadata_entries)

    table_metadata_entries_dict = table_metadata_entries.dict()
    with pytest.raises(DagsterInvalidMetadata):
        AssetMaterialization(asset_key="a", metadata=table_metadata_entries_dict)

    assert dict(TableMetadataEntries()) == {}
    assert TableMetadataEntries.extract(dict(TableMetadataEntries())) == TableMetadataEntries()


def test_column_lineage():
    column_lineages = TableColumnLineages(
        column_lineages={"foo": [AssetColumnDep(asset_key=AssetKey("abc"), column_name="id")]}
    )
    table_metadata_entries = TableMetadataEntries(column_lineages=column_lineages)

    dict_table_metadata_entries = dict(table_metadata_entries)
    assert dict_table_metadata_entries == {
        "dagster/column_lineages": JsonMetadataValue(column_lineages.dict())
    }
    assert isinstance(dict_table_metadata_entries["dagster/column_lineages"], JsonMetadataValue)
    mat = AssetMaterialization(asset_key="a", metadata=dict_table_metadata_entries)
    extracted = TableMetadataEntries.extract(mat.metadata).column_lineages
    assert extracted == column_lineages
    assert isinstance(extracted, TableColumnLineages)

    splat_table_metadata_entries = {**table_metadata_entries}
    assert splat_table_metadata_entries == {
        "dagster/column_lineages": JsonMetadataValue(column_lineages.dict())
    }
    assert isinstance(splat_table_metadata_entries["dagster/column_lineages"], JsonMetadataValue)
    mat = AssetMaterialization(asset_key="a", metadata=splat_table_metadata_entries)
    extracted = TableMetadataEntries.extract(mat.metadata).column_lineages
    assert extracted == column_lineages
    assert isinstance(extracted, TableColumnLineages)
