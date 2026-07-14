# Custom index definitions

`curated/` contains reviewed, version-controlled custom index JSON definitions.
`local/` contains indexes saved by a local Streamlit process and is intentionally
ignored by version control. To promote a local index, validate it with the test
suite, move it into `curated/`, and commit the JSON definition.

Local files are an MVP development store. Streamlit Community Cloud filesystems
are ephemeral and do not provide durable, shared, multi-user persistence. Replace
the storage adapter with a database-backed implementation before public launch.
