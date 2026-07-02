"""Utility functions for tool output management and result formatting."""

import json
from typing import Any


def truncate_string(text: str, max_length: int = 5000) -> str:
    """
    Truncate a string to a maximum length.

    Args:
        text: String to truncate
        max_length: Maximum allowed length (default: 5000)

    Returns:
        Truncated string with indication if truncated
    """
    if len(text) <= max_length:
        return text

    return f"{text[:max_length]}\n\n... [Output truncated. Original length: {len(text)} characters, showing first {max_length} characters]"


def limit_list_items(items: list[Any], max_items: int = 50) -> tuple[list[Any], bool]:
    """
    Limit the number of items in a list.

    Args:
        items: List to limit
        max_items: Maximum number of items (default: 50)

    Returns:
        Tuple of (limited list, was_truncated boolean)
    """
    if len(items) <= max_items:
        return items, False

    return items[:max_items], True


def limit_dict_result(
    result: dict[str, Any],
    list_keys: list[str] | None = None,
    max_items: int = 50,
    max_string_length: int = 5000,
) -> dict[str, Any]:
    """
    Limit the size of dictionary results to prevent context flooding.

    Args:
        result: Dictionary result to limit
        list_keys: List of keys that contain lists to limit (e.g., ['hits', 'pods', 'events'])
        max_items: Maximum items in lists
        max_string_length: Maximum length for string values

    Returns:
        Limited dictionary with metadata about truncation
    """
    limited_result = result.copy()
    truncation_info = {}

    # Handle list limiting
    if list_keys:
        for key in list_keys:
            if key in limited_result and isinstance(limited_result[key], list):
                # Reduce list items to messages when available
                reduced_items: list[Any] = []
                for item in limited_result[key]:
                    if isinstance(item, dict):
                        if "message" in item and isinstance(item["message"], str):
                            reduced_items.append(item["message"])
                            continue
                        source = item.get("_source")
                        if isinstance(source, dict) and isinstance(
                            source.get("message"), str
                        ):
                            reduced_items.append(source["message"])
                            continue
                    reduced_items.append(item)
                limited_result[key] = reduced_items
                original_count = len(limited_result[key])
                limited_result[key], was_truncated = limit_list_items(
                    limited_result[key], max_items
                )
                if was_truncated:
                    truncation_info[key] = {
                        "original_count": original_count,
                        "displayed_count": max_items,
                        "truncated": True,
                    }

    # Handle string truncation for all string values
    for key, value in limited_result.items():
        if isinstance(value, str) and len(value) > max_string_length:
            limited_result[key] = truncate_string(value, max_string_length)
            truncation_info[key] = {
                "original_length": len(value),
                "displayed_length": max_string_length,
                "truncated": True,
            }

    # Add truncation metadata if any truncation occurred
    if truncation_info:
        limited_result["_truncation_info"] = truncation_info

    return limited_result


def format_result_summary(
    result: dict[str, Any],
    summary_fields: list[str] | None = None,
) -> str:
    """
    Format a result dictionary into a concise summary string.

    Args:
        result: Dictionary result to format
        summary_fields: List of important fields to highlight in summary

    Returns:
        Formatted summary string
    """
    summary_parts = []

    # Add summary fields if specified
    if summary_fields:
        for field in summary_fields:
            if field in result:
                value = result[field]
                if isinstance(value, (list, dict)):
                    count = len(value)
                    summary_parts.append(f"{field}: {count} items")
                else:
                    summary_parts.append(f"{field}: {value}")

    # Add truncation info if present
    if "_truncation_info" in result:
        truncation = result["_truncation_info"]
        for key, info in truncation.items():
            if "original_count" in info:
                summary_parts.append(
                    f"[{key} truncated: showing {info['displayed_count']}/{info['original_count']} items]"
                )
            elif "original_length" in info:
                summary_parts.append(
                    f"[{key} truncated: showing {info['displayed_length']}/{info['original_length']} characters]"
                )

    if summary_parts:
        return "\n" + "\n".join(summary_parts) + "\n"

    return ""


def format_tool_result(
    description: str,
    result: dict[str, Any],
    list_keys: list[str] | None = None,
    summary_fields: list[str] | None = None,
    max_items: int = 50,
    max_string_length: int = 5000,
) -> str:
    """
    Format a tool result with proper limiting and summary.

    Args:
        description: Description prefix for the result
        result: Result dictionary from API
        list_keys: Keys containing lists to limit
        summary_fields: Fields to highlight in summary
        max_items: Maximum items in lists
        max_string_length: Maximum string length

    Returns:
        Formatted result string with limits applied
    """
    # Limit the result
    limited_result = limit_dict_result(
        result,
        list_keys=list_keys,
        max_items=max_items,
        max_string_length=max_string_length,
    )

    # Generate summary
    summary = format_result_summary(limited_result, summary_fields=summary_fields)

    # Format final output
    result_json = json.dumps(limited_result, indent=2, ensure_ascii=False)
    result_str = truncate_string(result_json, max_string_length)

    return f"{description}{summary}\n{result_str}"
