## BHoM data

- Revit Parquet files in the `revit_files` volumes are bronze and read-only. Flat tables that engineers write from them are silver. BHoM tables are gold, and production code reads gold.
- Use `bhom_schema.tables` for the DDL of BHoM tables and `bhom_schema.mapping` for mappings. Do not write `CREATE TABLE` for a BHoM class by hand.
- Units in gold are the units of the BHoM property.
- Install the package in a notebook with `%pip install --upgrade --pre --no-cache-dir --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "bhom-schema[mapping]"` in a cell of its own,
  then `dbutils.library.restartPython()` in the next cell.
- When the engineer has just created or changed a flat table in a notebook, mention once, in one line, that they can ask `@bhom-mapping check <table>` to see whether it is BHoM-aligned. Do not repeat it in the same chat.
- For mapping work, use the `bhom-mapping` skill.
