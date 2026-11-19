"""Mappings from a flat silver table to BHoM classes: the file format and its rules, the tools to look at the table and the classes, and applying, validating and writing a mapping."""

from bhom_schema.mapping.alignment import Alignment, alignment
from bhom_schema.mapping.apply import Applied, AppliedEntity, GoldObject, Problem, apply_mapping, gold_id, gold_table
from bhom_schema.mapping.catalog import ClassCard, ClassSummary, PropertyEntry, PropertyMatch, describe_class, schema_classes, schema_overview, search_properties
from bhom_schema.mapping.files import find_mapping, load_mapping, mapping_path, save_mapping
from bhom_schema.mapping.frames import FrameReport, validate_dataframe
from bhom_schema.mapping.gold import GoldRefused, GoldResult, write_gold
from bhom_schema.mapping.model import ColumnMapping, EntityMapping, MappingError, TableMapping, parse_mapping
from bhom_schema.mapping.profile import ColumnProfile, KeyCheck, KeyConflict, TableProfile, check_key, check_key_rows, profile, profile_rows, sample_rows
from bhom_schema.mapping.validate import EntityReport, MappingReport, validate_mapping, validate_rows

__all__ = [
    "Alignment", "Applied", "AppliedEntity", "ClassCard", "ClassSummary", "ColumnMapping", "ColumnProfile", "EntityMapping", "EntityReport", "FrameReport", "GoldObject", "GoldRefused", "GoldResult",
    "KeyCheck", "KeyConflict", "MappingError", "MappingReport", "Problem", "PropertyEntry", "PropertyMatch", "TableMapping", "TableProfile", "alignment", "apply_mapping", "check_key",
    "check_key_rows", "describe_class", "find_mapping", "gold_id", "gold_table", "load_mapping", "mapping_path", "parse_mapping", "profile", "profile_rows", "sample_rows", "save_mapping",
    "schema_classes", "schema_overview", "search_properties", "validate_dataframe", "validate_mapping", "validate_rows", "write_gold",
]
