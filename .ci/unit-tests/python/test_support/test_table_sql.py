"""The SQL of bhom_schema.tables: CREATE TABLE for a class, and the comparison of an existing table with a class that leads to ALTER TABLE ADD COLUMNS.

They run against the classes of the FixtureAlpha_oM assembly that the package carries.
"""

from __future__ import annotations

import pytest

from bhom_schema._version import __version__
from bhom_schema.FixtureAlpha_oM.Beam import Beam
from bhom_schema.FixtureAlpha_oM.CycleA import CycleA
from bhom_schema.FixtureAlpha_oM.LineLike import LineLike
from bhom_schema.FixtureAlpha_oM.PointLike import PointLike
from bhom_schema.FixtureAlpha_oM.Scalars import Scalars
from bhom_schema.FixtureAlpha_oM.Wrapper_1 import Wrapper_1
from bhom_schema.tables import BASE_SKIPPED, Json, Ref, Skip, Struct, UndecidedField, UnmappedType, add_columns_sql, check_table, create_table_sql

VERSION_COMMENT = "COMMENT 'Optional version of BHoM used as part of automatic versioning and schema upgrades.'"
POINT = Ref("main.default.PointLike")

def test_create_table_for_a_class_with_refs():
    """Checks the whole statement for LineLike with its two points stored as Refs: quoted names, the added key, comments, the table comment and the properties.

    Protects the text of the statement that users run, which the SQL tests of every other class build on.
    """
    sql = create_table_sql(LineLike, "main.default.LineLike", fields={"Start": POINT, "End": POINT})

    assert sql == (
        "CREATE TABLE IF NOT EXISTS `main`.`default`.`LineLike` (\n"
        "  `_id` STRING NOT NULL COMMENT 'Key of the row.',\n"
        f"  `_bhomVersion` STRING {VERSION_COMMENT},\n"
        "  `Start_id` STRING,\n"
        "  `End_id` STRING,\n"
        "  `Infinite` BOOLEAN COMMENT 'Extends the line to infinity.',\n"
        "  `Label` STRING\n"
        ")\n"
        "USING DELTA\n"
        "COMMENT 'A straight segment between two points.'\n"
        f"TBLPROPERTIES ('bhom.type' = 'BH.oM.FixtureAlpha.LineLike', 'bhom.schema_version' = '{__version__}')")

def test_create_table_for_a_class_with_structs_quotes_the_keyword_names():
    """Checks LineLike with its points as Structs, and that `End` (a SQL keyword) is quoted as a column and inside the struct type, and that replace writes CREATE OR REPLACE.

    Protects the Struct statement, and the quoting that field names such as End and Key need.
    """
    sql = create_table_sql(LineLike, "main.default.LineLike", fields={"Start": Struct(), "End": Struct()}, replace=True)
    point = "STRUCT<`X`: DOUBLE, `Y`: DOUBLE, `Z`: DOUBLE>"

    assert sql.startswith("CREATE OR REPLACE TABLE `main`.`default`.`LineLike` (\n")
    assert f"  `Start` {point},\n" in sql
    assert f"  `End` {point},\n" in sql

def test_create_table_for_a_class_without_a_description():
    """Checks PointLike: no table comment line, a type override for X, and the `_bhomVersion` column.

    Protects the optional parts of the statement, and the `types` override.
    """
    sql = create_table_sql(PointLike, "main.default.PointLike", types={"X": "FLOAT"})

    assert sql == (
        "CREATE TABLE IF NOT EXISTS `main`.`default`.`PointLike` (\n"
        "  `_id` STRING NOT NULL COMMENT 'Key of the row.',\n"
        f"  `_bhomVersion` STRING {VERSION_COMMENT},\n"
        "  `X` FLOAT,\n"
        "  `Y` DOUBLE,\n"
        "  `Z` DOUBLE\n"
        ")\n"
        "USING DELTA\n"
        f"TBLPROPERTIES ('bhom.type' = 'BH.oM.FixtureAlpha.PointLike', 'bhom.schema_version' = '{__version__}')")

def test_create_table_for_a_bhomobject_keys_on_its_guid_and_comments_the_unit():
    """Checks Beam: the BHoM_Guid is the NOT NULL key and first, no `_id` is added, skipped fields have no column, and the quantity and display text are in the comment of Span.

    Protects the key rule for BHoMObject classes and the column comments.
    """
    sql = create_table_sql(Beam, "main.default.Beam", fields={**BASE_SKIPPED, "Start": Skip()})
    lines = sql.splitlines()

    assert lines[1] == "  `BHoM_Guid` STRING NOT NULL,"
    assert "`_id`" not in sql
    assert "`Fragments`" not in sql
    assert "`CustomData`" not in sql
    assert "`Start" not in sql
    assert "  `Span` DOUBLE COMMENT 'Span length. Distance between the supports. [Length, m]'," in lines
    assert "  `Support` STRING COMMENT 'One of: None, Fixed, Pinned.'," in lines
    assert "  `Count` BIGINT," in lines
    assert "  `Small` FLOAT" in lines
    assert "  `Tags` ARRAY<STRING>," in lines

def test_create_table_for_scalars_maps_every_scalar_column():
    """Checks the columns of the Scalars fixture in the statement: timestamp, decimal, seconds, strings with a quote in the default, and a json column.

    Protects the scalar types end to end, from the Python annotation to the SQL text.
    """
    sql = create_table_sql(Scalars, "main.default.Scalars", fields={**BASE_SKIPPED, "Colour": Skip(), "TypeRef": Json(), "Callback": Skip()})
    lines = sql.splitlines()

    assert "  `Created` TIMESTAMP_NTZ," in lines
    assert "  `Key` STRING," in lines
    assert "  `Cost` DECIMAL(38,10)," in lines
    assert "  `Duration` DOUBLE COMMENT 'Seconds.'," in lines
    assert "  `Letter` STRING COMMENT 'One character.'," in lines
    assert "  `TypeRef` STRING," in lines

def test_the_key_can_be_another_field_or_left_out():
    """Checks `key=` with a field name (that column is NOT NULL and first) and with None (no key column, nothing NOT NULL).

    Protects the key choice of the statement.
    """
    named = create_table_sql(PointLike, "t.s.p", key="X").splitlines()
    none = create_table_sql(PointLike, "t.s.p", key=None)

    assert named[1] == "  `X` DOUBLE NOT NULL,"
    assert "NOT NULL" not in none
    assert "`_id`" not in none

def test_text_in_a_comment_is_escaped():
    """Checks that a quote, a backslash and a line break in a description cannot end the string literal of a comment.

    Protects the statement from being broken, or changed, by the text of a C# summary.
    """
    from bhom_schema.tables.sql import literal

    assert literal("it's a\\b\nc") == "'it\\'s a\\\\b\\nc'"

def test_a_table_name_is_quoted_part_by_part():
    """Checks that a one, two or three part name is quoted per part, that a name with backticks is kept, and that an empty part raises.

    Protects the statement against names that are keywords, and a typo such as `main..table`.
    """
    assert "`one`" in create_table_sql(PointLike, "one")
    assert "`s`.`t`" in create_table_sql(PointLike, "s.t")
    assert "`my catalog`.s.t" in create_table_sql(PointLike, "`my catalog`.s.t")

    with pytest.raises(ValueError, match="not a table name"):
        create_table_sql(PointLike, "main..table")

def test_an_undecided_field_stops_create_table_with_the_listing_error():
    """Checks that LineLike with no decisions, and CycleA with an unfinished Struct, raise UnmappedType with the fields listed, and that a generic class is refused.

    Protects the rule that no statement is written while a field has no decision.
    """
    with pytest.raises(UnmappedType, match=r"LineLike has 2 fields of a custom type[\s\S]*Start: PointLike[\s\S]*End: PointLike"):
        create_table_sql(LineLike, "main.default.LineLike")

    with pytest.raises(UnmappedType, match=r"Other\.Other: CycleA"):
        create_table_sql(CycleA, "main.default.CycleA", fields={"Other": Struct()})

    with pytest.raises(UnmappedType, match="generic class"):
        create_table_sql(Wrapper_1, "main.default.Wrapper")  # pyright: ignore[reportArgumentType]

def test_a_type_override_for_an_unknown_or_skipped_field_is_refused():
    """Checks that `types=` raises for a name the class does not have and for a field that a Skip leaves without a column.

    Protects the override from a typo that would silently change nothing.
    """
    with pytest.raises(ValueError, match="no field 'Nope'"):
        create_table_sql(PointLike, "t.s.p", types={"Nope": "INT"})

    with pytest.raises(ValueError, match="no column to give a type"):
        create_table_sql(PointLike, "t.s.p", fields={"Z": Skip()}, types={"Z": "INT"})

def test_check_table_of_a_matching_table_is_ok():
    """Checks that the columns of a table made by create_table_sql, as DESCRIBE writes them (lower case types, no spaces in a struct), match the class.

    Protects the comparison from reporting differences in spelling, and the `ok` and text of a clean result.
    """
    columns = {
        "_id": "string", "_bhomVersion": "string", "Start": "struct<X:double,Y:double,Z:double>", "End_id": "string", "Infinite": "boolean", "Label": "string"}
    check = check_table(LineLike, columns, fields={"Start": Struct(), "End": POINT})

    assert check.ok
    assert check.missing == [] and check.extra == [] and check.mismatched == [] and check.undecided_fields == []
    assert str(check) == "the table matches the class"

def test_check_table_reports_missing_extra_and_mismatched_columns():
    """Checks a table with a column of another type, a column the class lacks and two columns that are absent, and that names are matched without regard to case.

    Protects the readable report that tells the user whether a table written by an older alpha or by hand will read as the class.
    """
    check = check_table(PointLike, {"_ID": "STRING", "x": "double", "Y": "int", "Extra": "string"})

    assert not check.ok
    assert [column.name for column in check.missing] == ["_bhomVersion", "Z"]
    assert check.extra == ["Extra"]
    assert [(column.name, actual) for column, actual in check.mismatched] == [("Y", "int")]
    assert str(check) == (
        "missing column _bhomVersion STRING\n"
        "missing column Z DOUBLE\n"
        "column Y is int, the class expects DOUBLE\n"
        "extra column Extra, which the class does not store")

def test_check_table_lists_undecided_fields_and_ignores_extra_columns_for_ok():
    """Checks that an undecided field is listed (not raised) and makes the check not ok, that a skipped field's column is extra, and that extra alone does not fail it.

    Protects the use of check_table before every decision is made, and the meaning of `ok`: the table reads as the class.
    """
    undecided = check_table(LineLike, {"_id": "string"})

    assert undecided.undecided_fields == [UndecidedField("Start", "PointLike"), UndecidedField("End", "PointLike")]
    assert not undecided.ok

    skipped = check_table(PointLike, {"_id": "string", "_bhomVersion": "string", "X": "double", "Y": "double", "Z": "double"}, fields={"Z": Skip()})

    assert skipped.extra == ["Z"]
    assert skipped.ok

def test_check_table_applies_the_type_overrides():
    """Checks that a table made with `types=` matches only when the same override is given to check_table.

    Protects the pair create_table_sql and check_table from disagreeing about a column the user typed by hand.
    """
    columns = {"_id": "string", "_bhomVersion": "string", "X": "float", "Y": "double", "Z": "double"}

    assert not check_table(PointLike, columns).ok
    assert check_table(PointLike, columns, types={"X": "FLOAT"}).ok

def test_add_columns_sql_adds_the_missing_columns_as_nullable_columns():
    """Checks the ALTER statement for a table that lacks `_bhomVersion` and Z, that the key is added without NOT NULL, and that a complete table gives None.

    Protects the upgrade path of a table when a new alpha adds a property to a class.
    """
    check = check_table(PointLike, {"_id": "string", "X": "double", "Y": "double"})

    assert add_columns_sql(check, "main.default.PointLike") == (
        f"ALTER TABLE `main`.`default`.`PointLike` ADD COLUMNS (`_bhomVersion` STRING {VERSION_COMMENT}, `Z` DOUBLE)")

    keyless = check_table(PointLike, {"X": "double", "Y": "double", "Z": "double", "_bhomVersion": "string"})

    assert add_columns_sql(keyless, "main.default.PointLike") == "ALTER TABLE `main`.`default`.`PointLike` ADD COLUMNS (`_id` STRING COMMENT 'Key of the row.')"
    assert add_columns_sql(check_table(PointLike, {"_id": "string", "_bhomVersion": "string", "X": "double", "Y": "double", "Z": "double"}), "main.default.PointLike") is None
