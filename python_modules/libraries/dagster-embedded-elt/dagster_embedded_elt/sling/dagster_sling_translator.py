import re
from typing import Any, Iterable, Mapping, Optional

from dagster import (
    AssetKey,
    AutoMaterializePolicy,
    FreshnessPolicy,
    MetadataValue,
)
from dagster._annotations import public


class DagsterSlingTranslator:
    def __init__(self, target_prefix="target"):
        """A class that allows customization of how to map a Sling stream to a Dagster AssetKey.

        Args:
            target_prefix (str): The prefix to use when creating the AssetKey
        """
        self.target_prefix = target_prefix

    @public
    @classmethod
    def sanitize_stream_name(cls, stream_name: str) -> str:
        """A function that takes a stream name from a Sling replication config and returns a
        sanitized name for the stream.
        By default, this removes any non-alphanumeric characters from the stream name and replaces
        them with underscores, while removing any double quotes.

        Args:
            stream_name (str):  A stream name to sanitize
        """
        return re.sub(r"[^a-zA-Z0-9_.]", "_", stream_name.replace('"', ""))

    @public
    def get_asset_key(self, stream_definition: Mapping[str, Any]) -> AssetKey:
        """A function that takes a stream definition from a Sling replication config and returns a
        Dagster AssetKey.

        The stream definition is a dictionary key/value pair where the key is the stream name and
        the value is a dictionary representing the stream definition. For example:

        stream_definition = {"public.users": {'sql': 'select all_user_id, name from public."all_Users"', 'object': 'public.all_users'}}

        By default, this returns the class's target_prefix paramater concatenated with the stream name. For example, a stream
        named "public.accounts" will create an AssetKey named "target_public_accounts".

        By default, this returns the target_prefix concatenated with the stream name. For example, a stream
        named "public.accounts" will create an AssetKey named "target_public_accounts".

        Override this function to customize how to map a Sling stream to a Dagster AssetKey.
        Alternatively, you can provide metadata in your Sling replication config to specify the
        Dagster AssetKey for a stream as follows:

        public.users:
           meta:
             dagster:
               asset_key: "mydb_users"

        Args:
            stream_definition (Mapping[str, Any]): A dictionary representing the stream definition
            target_prefix (str): The prefix to use when creating the AssetKey

        Returns:
            AssetKey: The Dagster AssetKey for the replication stream.

        Examples:
            Using a custom mapping for streams:

            class CustomSlingTranslator(DagsterSlingTranslator):
                @classmethod
                def get_asset_key_for_target(cls, stream_definition) -> AssetKey:
                    map = {"stream1": "asset1", "stream2": "asset2"}
                    return AssetKey(map[stream_name])
        """
        config = stream_definition.get("config", {}) or {}
        meta = config.get("meta", {})
        asset_key = meta.get("dagster", {}).get("asset_key")

        if asset_key:
            if self.sanitize_stream_name(asset_key) != asset_key:
                raise ValueError(
                    f"Asset key {asset_key} for stream {stream_definition['name']} is not "
                    "sanitized. Please use only alphanumeric characters and underscores."
                )
            return AssetKey(asset_key.split("."))

        stream_name = stream_definition["name"]
        sanitized_components = self.sanitize_stream_name(stream_name).split(".")
        return AssetKey([self.target_prefix] + sanitized_components)

    @public
    @classmethod
    def get_deps_asset_key(cls, stream_definition: Mapping[str, Any]) -> Iterable[AssetKey]:
        """A function that takes a stream name from a Sling replication config and returns a
        Dagster AssetKey for the dependencies of the replication stream.

        By default, this returns the stream name. For example, a stream
        named "public.accounts" will create an AssetKey named "target_public_accounts" and a
        depenency AssetKey named "public_accounts".

        Override this function to customize how to map a Sling stream to a Dagster AssetKey.
        Alternatively, you can provide metadata in your Sling replication config to specify the
        Dagster AssetKey for a stream as follows:

        public.users:
           meta:
             dagster:
               deps: "sourcedb_users"

        Args:
            stream_name (str): The name of the stream.

        Returns:
            AssetKey: The Dagster AssetKey dependency for the replication stream.

        Examples:
            Using a custom mapping for streams:

            class CustomSlingTranslator(DagsterSlingTranslator):
                @classmethod
                def get_deps_asset_key(cls, stream_name: str) -> AssetKey:
                    map = {"stream1": "asset1", "stream2": "asset2"}
                    return AssetKey(map[stream_name])


        """
        config = stream_definition.get("config", {}) or {}
        meta = config.get("meta", {})
        deps = meta.get("dagster", {}).get("deps")
        deps_out = []
        if deps and isinstance(deps, str):
            deps = [deps]
        if deps:
            assert isinstance(deps, list)
            for asset_key in deps:
                if cls.sanitize_stream_name(asset_key) != asset_key:
                    raise ValueError(
                        f"Deps Asset key {asset_key} for stream {stream_definition['name']} is not "
                        "sanitized. Please use only alphanumeric characters and underscores."
                    )
                deps_out.append(AssetKey(asset_key.split(".")))
            return deps_out

        stream_name = stream_definition["name"]
        components = cls.sanitize_stream_name(stream_name).split(".")
        return [AssetKey(components)]

    @classmethod
    @public
    def get_description(cls, stream_definition: Mapping[str, Any]) -> Optional[str]:
        config = stream_definition.get("config", {}) or {}
        if "sql" in config:
            return config["sql"]
        meta = config.get("meta", {})
        description = meta.get("dagster", {}).get("description")
        return description

    @classmethod
    @public
    def get_metadata(cls, stream_definition: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"stream_config": MetadataValue.json(stream_definition.get("config", {}))}

    @classmethod
    @public
    def get_group_name(cls, stream_definition: Mapping[str, Any]) -> Optional[str]:
        config = stream_definition.get("config", {}) or {}
        meta = config.get("meta", {})
        return meta.get("dagster", {}).get("group")

    @classmethod
    @public
    def get_freshness_policy(
        cls, stream_definition: Mapping[str, Any]
    ) -> Optional[FreshnessPolicy]:
        config = stream_definition.get("config", {}) or {}
        meta = config.get("meta", {})
        freshness_policy_config = meta.get("dagster", {}).get("freshness_policy")
        if freshness_policy_config:
            return FreshnessPolicy(
                maximum_lag_minutes=float(freshness_policy_config["maximum_lag_minutes"]),
                cron_schedule=freshness_policy_config.get("cron_schedule"),
                cron_schedule_timezone=freshness_policy_config.get("cron_schedule_timezone"),
            )

    @classmethod
    @public
    def get_auto_materialize_policy(
        cls, stream_definition: Mapping[str, Any]
    ) -> Optional[AutoMaterializePolicy]:
        config = stream_definition.get("config", {}) or {}
        meta = config.get("meta", {})
        auto_materialize_policy_config = meta.get("dagster", {}).get("auto_materialize_policy")
        if auto_materialize_policy_config:
            return AutoMaterializePolicy.eager()
