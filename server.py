"""Snipe-IT MCP Server

A Model Context Protocol (MCP) server for managing Snipe-IT inventory.
Provides tools for CRUD operations on Assets and Consumables.
"""

import os
import logging
import re
from typing import Literal, Annotated, Any, Optional
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

from fastmcp import FastMCP
from snipeit import SnipeIT
from snipeit.exceptions import (
    SnipeITException,
    SnipeITNotFoundError,
    SnipeITAuthenticationError,
    SnipeITValidationError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    name="Snipe-IT MCP Server"
)

# Get Snipe-IT configuration from environment variables
SNIPEIT_URL = os.getenv("SNIPEIT_URL")
SNIPEIT_TOKEN = os.getenv("SNIPEIT_TOKEN")

if not SNIPEIT_URL or not SNIPEIT_TOKEN:
    logger.warning(
        "SNIPEIT_URL and SNIPEIT_TOKEN environment variables must be set. "
        "Server will start but tools will fail until these are configured."
    )

# Initialize Snipe-IT client (will be used in tools)
def get_snipeit_client() -> SnipeIT:
    """Get or create a Snipe-IT client instance."""
    if not SNIPEIT_URL or not SNIPEIT_TOKEN:
        raise SnipeITException(
            "Snipe-IT credentials not configured. "
            "Please set SNIPEIT_URL and SNIPEIT_TOKEN environment variables."
        )
    return SnipeIT(url=SNIPEIT_URL, token=SNIPEIT_TOKEN)


# ============================================================================
# Pydantic Models for Tool Input/Output
# ============================================================================

def _normalize_choice(value: str | None, valid_choices: list[str], field_name: str) -> str | None:
    """Case/whitespace-insensitively resolve `value` to its canonical entry in `valid_choices`.

    Snipe-IT's enum-like fields (category_type, status type, custom field element/format, ...)
    are case-sensitive on the API side, but an LLM caller will often supply a differently-cased
    or title-cased variant (e.g. "Asset" instead of "asset"). Normalizing here means the tool
    schema still advertises the exact expected values (via Literal) while still accepting the
    obvious near-misses instead of round-tripping a cryptic API validation error.
    """
    if value is None:
        return None
    stripped = value.strip()
    for canonical in valid_choices:
        if stripped.lower() == canonical.lower():
            return canonical
    raise ValueError(f"Invalid {field_name} '{value}'. Must be one of: {', '.join(valid_choices)}")


class AssetData(BaseModel):
    """Model for asset data used in create/update operations."""
    status_id: int | None = Field(None, description="ID of the status label")
    model_id: int | None = Field(None, description="ID of the asset model")
    asset_tag: str | None = Field(None, description="Asset tag identifier")
    name: str | None = Field(None, description="Asset name")
    serial: str | None = Field(None, description="Serial number")
    purchase_date: str | None = Field(None, description="Purchase date (YYYY-MM-DD)")
    purchase_cost: float | None = Field(None, description="Purchase cost")
    order_number: str | None = Field(None, description="Order number")
    notes: str | None = Field(None, description="Additional notes")
    warranty_months: int | None = Field(None, description="Warranty period in months")
    location_id: int | None = Field(None, description="Location ID")
    rtd_location_id: int | None = Field(None, description="Default location ID")
    supplier_id: int | None = Field(None, description="Supplier ID")
    company_id: int | None = Field(None, description="Company ID")
    requestable: bool | None = Field(None, description="Whether asset is requestable")


class CheckoutData(BaseModel):
    """Model for asset checkout operations."""
    checkout_to_type: Literal["user", "asset", "location"] = Field(
        ...,
        description="Type of entity to checkout to. Must be exactly one of: user, asset, location."
    )
    assigned_to_id: int = Field(..., description="ID of the user/asset/location")
    expected_checkin: str | None = Field(None, description="Expected checkin date (YYYY-MM-DD)")
    checkout_at: str | None = Field(None, description="Checkout date (YYYY-MM-DD)")
    note: str | None = Field(None, description="Checkout notes")
    name: str | None = Field(None, description="Name for the checkout")

    @field_validator("checkout_to_type", mode="before")
    @classmethod
    def _normalize_checkout_to_type(cls, v):
        if isinstance(v, str):
            return _normalize_choice(v, ["user", "asset", "location"], "checkout_to_type")
        return v


class CheckinData(BaseModel):
    """Model for asset checkin operations."""
    note: str | None = Field(None, description="Checkin notes")
    location_id: int | None = Field(None, description="Location ID to checkin to")


class AuditData(BaseModel):
    """Model for asset audit operations."""
    location_id: int | None = Field(None, description="Location ID")
    note: str | None = Field(None, description="Audit notes")
    next_audit_date: str | None = Field(None, description="Next audit date (YYYY-MM-DD)")


class MaintenanceData(BaseModel):
    """Model for asset maintenance records."""
    asset_improvement: str = Field(..., description="Type of maintenance/improvement")
    supplier_id: int = Field(..., description="Supplier ID")
    title: str = Field(..., description="Maintenance title")
    cost: float | None = Field(None, description="Maintenance cost")
    start_date: str | None = Field(None, description="Start date (YYYY-MM-DD)")
    completion_date: str | None = Field(None, description="Completion date (YYYY-MM-DD)")
    notes: str | None = Field(None, description="Maintenance notes")


class ConsumableData(BaseModel):
    """Model for consumable data used in create/update operations."""
    name: str | None = Field(None, description="Consumable name")
    qty: int | None = Field(None, description="Quantity")
    category_id: int | None = Field(None, description="Category ID")
    company_id: int | None = Field(None, description="Company ID")
    location_id: int | None = Field(None, description="Location ID")
    manufacturer_id: int | None = Field(None, description="Manufacturer ID")
    model_number: str | None = Field(None, description="Model number")
    item_no: str | None = Field(None, description="Item number")
    order_number: str | None = Field(None, description="Order number")
    purchase_date: str | None = Field(None, description="Purchase date (YYYY-MM-DD)")
    purchase_cost: float | None = Field(None, description="Purchase cost")
    min_amt: int | None = Field(None, description="Minimum quantity threshold")
    notes: str | None = Field(None, description="Additional notes")


class LabelAssetData(BaseModel):
    """Asset fields read off an NTUST label photo directly (the caller has vision and
    reads the label itself — no OCR pipeline involved)."""
    asset_tag: str | None = Field(None, description="Asset tag (財產編號)")
    serial: str | None = Field(None, description="Serial number (序號)")
    name: str | None = Field(None, description="Asset name (財產名稱)")
    purchase_date: str | None = Field(
        None,
        description=(
            "Acquisition date (取得日期) in YYYY-MM-DD format. If the label shows an ROC "
            "date (e.g. 107.07.06), convert it yourself: ROC year + 1911 = Gregorian year "
            "(107 -> 2018), giving 2018-07-06."
        ),
    )
    warranty_months: int | None = Field(None, description="Lifespan (年限) in months — convert years shown on the label to months (e.g. 4 years -> 48)")
    specs: str | None = Field(None, description="Specifications (規格)")
    custodian_unit: str | None = Field(None, description="Custodian unit (保管單位)")
    custodian: str | None = Field(None, description="Custodian name (保管人員)")
    funding_source: str | None = Field(None, description="Funding source (經費來源)")


# ============================================================================
# Additional Pydantic Models for New API Resources
# ============================================================================

class AccessoryData(BaseModel):
    """Model for accessory data used in create/update operations."""
    name: str | None = Field(None, description="Accessory name")
    qty: int | None = Field(None, description="Quantity")
    category_id: int | None = Field(None, description="Category ID")
    company_id: int | None = Field(None, description="Company ID")
    location_id: int | None = Field(None, description="Location ID")
    manufacturer_id: int | None = Field(None, description="Manufacturer ID")
    model_number: str | None = Field(None, description="Model number")
    order_number: str | None = Field(None, description="Order number")
    purchase_date: str | None = Field(None, description="Purchase date (YYYY-MM-DD)")
    purchase_cost: float | None = Field(None, description="Purchase cost")
    min_amt: int | None = Field(None, description="Minimum quantity threshold")
    notes: str | None = Field(None, description="Additional notes")
    supplier_id: int | None = Field(None, description="Supplier ID")


CATEGORY_TYPES = ["asset", "accessory", "consumable", "component", "license"]


class CategoryData(BaseModel):
    """Model for category data."""
    name: str | None = Field(None, description="Category name")
    category_type: Literal["asset", "accessory", "consumable", "component", "license"] | None = Field(
        None,
        description=(
            "Category type — which kind of item this category can be assigned to. "
            "Must be exactly one of (lowercase): asset, accessory, consumable, component, license. "
            "Required when creating a category; cannot be changed once the category is created."
        )
    )
    eula_text: str | None = Field(None, description="EULA text")
    use_default_eula: bool | None = Field(None, description="Use default EULA")
    require_acceptance: bool | None = Field(None, description="Require acceptance")
    checkin_email: bool | None = Field(None, description="Send checkin email")

    @field_validator("category_type", mode="before")
    @classmethod
    def _normalize_category_type(cls, v):
        if isinstance(v, str):
            return _normalize_choice(v, CATEGORY_TYPES, "category_type")
        return v


class CompanyData(BaseModel):
    """Model for company data."""
    name: str | None = Field(None, description="Company name")


class LicenseData(BaseModel):
    """Model for license data."""
    name: str | None = Field(None, description="License name")
    seats: int | None = Field(None, description="Number of seats")
    category_id: int | None = Field(None, description="Category ID")
    company_id: int | None = Field(None, description="Company ID")
    manufacturer_id: int | None = Field(None, description="Manufacturer ID")
    product_key: str | None = Field(None, description="Product key")
    order_number: str | None = Field(None, description="Order number")
    purchase_order: str | None = Field(None, description="Purchase order")
    purchase_date: str | None = Field(None, description="Purchase date (YYYY-MM-DD)")
    purchase_cost: float | None = Field(None, description="Purchase cost")
    notes: str | None = Field(None, description="Additional notes")
    expiration_date: str | None = Field(None, description="Expiration date (YYYY-MM-DD)")
    termination_date: str | None = Field(None, description="Termination date (YYYY-MM-DD)")
    depreciation_id: int | None = Field(None, description="Depreciation ID")
    supplier_id: int | None = Field(None, description="Supplier ID")
    maintained: bool | None = Field(None, description="Maintained")
    reassignable: bool | None = Field(None, description="Reassignable")


class LocationData(BaseModel):
    """Model for location data."""
    name: str | None = Field(None, description="Location name")
    address: str | None = Field(None, description="Address")
    address2: str | None = Field(None, description="Address line 2")
    city: str | None = Field(None, description="City")
    state: str | None = Field(None, description="State")
    country: str | None = Field(None, description="Country")
    zip: str | None = Field(None, description="Zip/postal code")
    parent_id: int | None = Field(None, description="Parent location ID")
    currency: str | None = Field(None, description="Currency code")
    ldap_ou: str | None = Field(None, description="LDAP OU")


class ManufacturerData(BaseModel):
    """Model for manufacturer data."""
    name: str | None = Field(None, description="Manufacturer name")
    url: str | None = Field(None, description="Manufacturer website")
    support_url: str | None = Field(None, description="Support URL")
    support_phone: str | None = Field(None, description="Support phone")
    support_email: str | None = Field(None, description="Support email")


class ModelData(BaseModel):
    """Model for asset model data."""
    name: str | None = Field(None, description="Model name")
    model_number: str | None = Field(None, description="Model number")
    category_id: int | None = Field(None, description="Category ID")
    manufacturer_id: int | None = Field(None, description="Manufacturer ID")
    eol: int | None = Field(None, description="End of life (months)")
    fieldset_id: int | None = Field(None, description="Fieldset ID")
    notes: str | None = Field(None, description="Notes")
    depreciation_id: int | None = Field(None, description="Depreciation ID")


STATUS_LABEL_TYPES = ["deployable", "pending", "undeployable", "archived"]


class StatusLabelData(BaseModel):
    """Model for status label data."""
    name: str | None = Field(None, description="Status label name")
    type: Literal["deployable", "pending", "undeployable", "archived"] | None = Field(
        None,
        description=(
            "Status type — controls whether assets with this label can be checked out. "
            "Must be exactly one of (lowercase): deployable (can be checked out), "
            "pending (not yet ready), undeployable (broken/lost/needs repair), "
            "archived (retired, hidden from most views). Required when creating a status label."
        )
    )
    color: str | None = Field(None, description="Color hex code")
    show_in_nav: bool | None = Field(None, description="Show in navigation")
    default_label: bool | None = Field(None, description="Default label")
    notes: str | None = Field(None, description="Notes")

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, v):
        if isinstance(v, str):
            return _normalize_choice(v, STATUS_LABEL_TYPES, "type")
        return v


class SupplierData(BaseModel):
    """Model for supplier data."""
    name: str | None = Field(None, description="Supplier name")
    address: str | None = Field(None, description="Address")
    address2: str | None = Field(None, description="Address line 2")
    city: str | None = Field(None, description="City")
    state: str | None = Field(None, description="State")
    country: str | None = Field(None, description="Country")
    zip: str | None = Field(None, description="Zip/postal code")
    phone: str | None = Field(None, description="Phone")
    fax: str | None = Field(None, description="Fax")
    email: str | None = Field(None, description="Email")
    contact: str | None = Field(None, description="Contact person")
    notes: str | None = Field(None, description="Notes")
    url: str | None = Field(None, description="Website URL")


class UserData(BaseModel):
    """Model for user data (POST/PATCH /api/v1/users)."""
    first_name: str | None = Field(None, description="First name (required on create)")
    last_name: str | None = Field(None, description="Last name")
    username: str | None = Field(None, description="Username (required on create unless LDAP)")
    password: str | None = Field(None, description="Password (required on create unless LDAP)")
    password_confirmation: str | None = Field(
        None, description="Must match password (auto-filled from password if omitted)"
    )
    email: str | None = Field(None, description="Email")
    permissions: dict[str, Any] | str | None = Field(None, description="Permissions map or JSON string")
    activated: bool | None = Field(None, description="Activated")
    phone: str | None = Field(None, description="Phone")
    mobile: str | None = Field(None, description="Mobile phone")
    jobtitle: str | None = Field(None, description="Job title")
    display_name: str | None = Field(None, description="Display name")
    manager_id: int | None = Field(None, description="Manager user ID")
    employee_num: str | None = Field(None, description="Employee number")
    notes: str | None = Field(None, description="Notes")
    company_id: int | None = Field(None, description="Primary company ID (legacy)")
    company_ids: list[int] | None = Field(None, description="Company IDs (preferred multi-company)")
    location_id: int | None = Field(None, description="Location ID")
    department_id: int | None = Field(None, description="Department ID")
    groups: list[int] | None = Field(None, description="Permission group IDs (superuser only)")
    remote: bool | None = Field(None, description="Remote worker")
    vip: bool | None = Field(None, description="VIP flag")
    autoassign_licenses: bool | None = Field(None, description="Auto-assign licenses")
    website: str | None = Field(None, description="Website URL")
    address: str | None = Field(None, description="Street address")
    city: str | None = Field(None, description="City")
    state: str | None = Field(None, description="State/province")
    country: str | None = Field(None, description="Country")
    zip: str | None = Field(None, description="Postal code")
    locale: str | None = Field(None, description="Locale")
    start_date: str | None = Field(None, description="Start date (Y-m-d)")
    end_date: str | None = Field(None, description="End date (Y-m-d)")
    send_welcome: bool | int | str | None = Field(
        None, description="Send welcome email on create (1/true when activated + email set)"
    )
    ldap_import: bool | None = Field(None, description="Mark as LDAP-imported (skips password requirement)")


class ComponentData(BaseModel):
    """Model for component data."""
    name: str | None = Field(None, description="Component name")
    qty: int | None = Field(None, description="Quantity")
    category_id: int | None = Field(None, description="Category ID")
    company_id: int | None = Field(None, description="Company ID")
    location_id: int | None = Field(None, description="Location ID")
    order_number: str | None = Field(None, description="Order number")
    purchase_date: str | None = Field(None, description="Purchase date (YYYY-MM-DD)")
    purchase_cost: float | None = Field(None, description="Purchase cost")
    min_amt: int | None = Field(None, description="Minimum quantity threshold")
    serial: str | None = Field(None, description="Serial number")


class DepartmentData(BaseModel):
    """Model for department data."""
    name: str | None = Field(None, description="Department name")
    company_id: int | None = Field(None, description="Company ID")
    location_id: int | None = Field(None, description="Location ID")
    manager_id: int | None = Field(None, description="Manager ID")
    notes: str | None = Field(None, description="Notes")


CUSTOM_FIELD_ELEMENTS = ["text", "listbox", "textarea", "markdown-textarea", "checkbox", "radio"]
CUSTOM_FIELD_FORMATS = [
    "ANY", "CUSTOM REGEX", "ALPHA", "ALPHA-DASH", "NUMERIC", "ALPHA-NUMERIC",
    "EMAIL", "DATE", "URL", "IP", "IPV4", "IPV6", "MAC", "BOOLEAN",
]


class CustomFieldData(BaseModel):
    """Model for custom field data."""
    name: str | None = Field(None, description="Field name")
    element: Literal["text", "listbox", "textarea", "markdown-textarea", "checkbox", "radio"] | None = Field(
        None,
        description=(
            "Field input type. Must be exactly one of (lowercase): text, listbox, textarea, "
            "markdown-textarea, checkbox, radio. Use listbox/radio with field_values for a "
            "fixed set of options. Required when creating a custom field."
        )
    )
    field_values: str | None = Field(None, description="Pipe-separated values for listbox/radio, e.g. 'Option A|Option B|Option C'")
    format: Literal[
        "ANY", "CUSTOM REGEX", "ALPHA", "ALPHA-DASH", "NUMERIC", "ALPHA-NUMERIC",
        "EMAIL", "DATE", "URL", "IP", "IPV4", "IPV6", "MAC", "BOOLEAN",
    ] | None = Field(
        None,
        description=(
            "Predefined validation format for the field's value. Must be exactly one of "
            "(uppercase): ANY, CUSTOM REGEX, ALPHA, ALPHA-DASH, NUMERIC, ALPHA-NUMERIC, EMAIL, "
            "DATE, URL, IP, IPV4, IPV6, MAC, BOOLEAN. Use 'CUSTOM REGEX' together with "
            "custom_format to supply your own regex pattern."
        )
    )
    custom_format: str | None = Field(None, description="Custom regex pattern, only used when format='CUSTOM REGEX'")
    field_encrypted: bool | None = Field(None, description="Whether field is encrypted")
    help_text: str | None = Field(None, description="Help text")
    show_in_email: bool | None = Field(None, description="Show in email notifications")

    @field_validator("element", mode="before")
    @classmethod
    def _normalize_element(cls, v):
        if isinstance(v, str):
            return _normalize_choice(v, CUSTOM_FIELD_ELEMENTS, "element")
        return v

    @field_validator("format", mode="before")
    @classmethod
    def _normalize_format(cls, v):
        if isinstance(v, str):
            return _normalize_choice(v, CUSTOM_FIELD_FORMATS, "format")
        return v


class FieldsetData(BaseModel):
    """Model for fieldset data."""
    name: str | None = Field(None, description="Fieldset name")


class GroupData(BaseModel):
    """Model for group data."""
    name: str | None = Field(None, description="Group name")
    permissions: dict | None = Field(None, description="Permissions object")


class DepreciationData(BaseModel):
    """Model for depreciation data."""
    name: str | None = Field(None, description="Depreciation name")
    months: int | None = Field(None, description="Number of months")


class MaintenanceTypeData(BaseModel):
    """Model for maintenance type data."""
    name: str | None = Field(None, description="Maintenance type name")


class KitData(BaseModel):
    """Model for kit (predefined kit) data."""
    name: str | None = Field(None, description="Kit name")


# ============================================================================
# Structured Error Responses
# ============================================================================

def _error(
    error_type: str,
    message: str,
    *,
    hint: str | None = None,
    allowed_values: dict[str, list[str]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standard structured error payload returned by every tool on failure.

    Keeps `success`/`error` for backward compatibility with existing callers while adding
    `status`/`error_type`/`message`/`hint`/`allowed_values` so an LLM caller can recover
    (e.g. re-query a list action for valid IDs/enum values) instead of parsing a flat string.
    """
    result: dict[str, Any] = {
        "success": False,
        "error": message,
        "status": "error",
        "error_type": error_type,
        "message": message,
    }
    if hint:
        result["hint"] = hint
    if allowed_values:
        result["allowed_values"] = allowed_values
    if extra:
        result.update(extra)
    return result


# Known enum-like fields Snipe-IT's API validates server-side, keyed by a keyword that
# tends to appear in the API's own error text, mapped to (allowed values, recovery hint).
_ENUM_FIELD_INFO: dict[str, tuple[list[str] | None, str]] = {
    "category type": (CATEGORY_TYPES, 'Query `manage_categories` (action="list") to see existing categories, or use one of the allowed values directly.'),
    "status label": (STATUS_LABEL_TYPES, 'Query `manage_status_labels` (action="list") to see valid status types or IDs before retrying.'),
    "status_id": (None, 'Query `manage_status_labels` (action="list") to see valid status IDs before retrying.'),
    "element": (CUSTOM_FIELD_ELEMENTS, "Use one of the allowed custom field element types."),
    "format": (CUSTOM_FIELD_FORMATS, "Use one of the allowed custom field format types."),
    "checkout_to_type": (["user", "asset", "location"], "Use one of the allowed checkout target types."),
}


def _snipeit_validation_error(
    e: Exception,
    *,
    prefix: str = "Validation error",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured VALIDATION_FAILED response from a Snipe-IT API validation error.

    Snipe-IT's own error text (e.g. "The selected category type is invalid.") only loosely
    names the offending field, so this matches on known keywords to attach a `hint` and
    `allowed_values` instead of leaving the caller to guess at a second attempt.
    """
    text = str(e)
    message = f"{prefix}: {text}"
    haystack = text.lower()
    for keyword, (allowed, hint) in _ENUM_FIELD_INFO.items():
        if keyword in haystack:
            allowed_values = {keyword.replace(" ", "_"): allowed} if allowed else None
            return _error("VALIDATION_FAILED", message, hint=hint, allowed_values=allowed_values, extra=extra)
    return _error("VALIDATION_FAILED", message, extra=extra)


# ============================================================================
# Asset Tools
# ============================================================================

@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
    }
)
def manage_assets(
    action: Annotated[
        Literal["create", "get", "list", "update", "delete"],
        "The action to perform on assets"
    ],
    asset_id: Annotated[int | None, "Asset ID (required for get, update, delete)"] = None,
    asset_tag: Annotated[str | None, "Asset tag (alternative to asset_id for get)"] = None,
    serial: Annotated[str | None, "Serial number (alternative to asset_id for get)"] = None,
    asset_data: Annotated[AssetData | None, "Asset data (required for create, optional for update)"] = None,
    limit: Annotated[int | None, "Number of results to return (for list action)"] = 50,
    offset: Annotated[int | None, "Number of results to skip (for list action)"] = 0,
    search: Annotated[str | None, "Search query (for list action)"] = None,
    sort: Annotated[str | None, "Field to sort by (for list action)"] = None,
    order: Annotated[Literal["asc", "desc"] | None, "Sort order (for list action)"] = None,
) -> dict[str, Any]:
    """Manage Snipe-IT assets with CRUD operations.
    
    This tool handles all basic asset operations:
    - create: Create a new asset (requires asset_data with at least status_id and model_id)
    - get: Retrieve a single asset by ID, asset_tag, or serial number
    - list: List assets with optional pagination and filtering
    - update: Update an existing asset (requires asset_id and asset_data)
    - delete: Delete an asset (requires asset_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not asset_data:
                    return _error("MISSING_PARAMETER", "asset_data is required for create action")
                
                if not asset_data.status_id or not asset_data.model_id:
                    return _error("MISSING_PARAMETER", "status_id and model_id are required to create an asset")
                
                # Build creation payload
                create_kwargs = {k: v for k, v in asset_data.model_dump().items() if v is not None}
                asset = client.assets.create(**create_kwargs)
                
                return {
                    "success": True,
                    "action": "create",
                    "asset": {
                        "id": asset.id,
                        "asset_tag": getattr(asset, "asset_tag", None),
                        "name": getattr(asset, "name", None),
                        "serial": getattr(asset, "serial", None),
                    }
                }
            
            elif action == "get":
                if asset_tag:
                    asset = client.assets.get_by_tag(asset_tag)
                elif serial:
                    asset = client.assets.get_by_serial(serial)
                elif asset_id:
                    asset = client.assets.get(asset_id)
                else:
                    return _error("MISSING_PARAMETER", "One of asset_id, asset_tag, or serial is required for get action")
                
                # Extract asset data
                asset_dict = {
                    "id": asset.id,
                    "asset_tag": getattr(asset, "asset_tag", None),
                    "name": getattr(asset, "name", None),
                    "serial": getattr(asset, "serial", None),
                    "model": getattr(asset, "model", None),
                    "status_label": getattr(asset, "status_label", None),
                    "category": getattr(asset, "category", None),
                    "manufacturer": getattr(asset, "manufacturer", None),
                    "supplier": getattr(asset, "supplier", None),
                    "notes": getattr(asset, "notes", None),
                    "location": getattr(asset, "location", None),
                    "assigned_to": getattr(asset, "assigned_to", None),
                    "purchase_date": getattr(asset, "purchase_date", None),
                    "purchase_cost": getattr(asset, "purchase_cost", None),
                }
                
                return {
                    "success": True,
                    "action": "get",
                    "asset": asset_dict
                }
            
            elif action == "list":
                params = {"limit": limit, "offset": offset}
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                assets = client.assets.list(**params)
                
                assets_list = [
                    {
                        "id": asset.id,
                        "asset_tag": getattr(asset, "asset_tag", None),
                        "name": getattr(asset, "name", None),
                        "serial": getattr(asset, "serial", None),
                        "model": getattr(asset, "model", {}).get("name") if hasattr(asset, "model") and isinstance(getattr(asset, "model", None), dict) else None,
                    }
                    for asset in assets
                ]
                
                return {
                    "success": True,
                    "action": "list",
                    "count": len(assets_list),
                    "assets": assets_list
                }
            
            elif action == "update":
                if not asset_id:
                    return _error("MISSING_PARAMETER", "asset_id is required for update action")
                if not asset_data:
                    return _error("MISSING_PARAMETER", "asset_data is required for update action")
                
                # Build update payload (only include non-None values)
                update_kwargs = {k: v for k, v in asset_data.model_dump().items() if v is not None}
                
                asset = client.assets.patch(asset_id, **update_kwargs)
                
                return {
                    "success": True,
                    "action": "update",
                    "asset": {
                        "id": asset.id,
                        "asset_tag": getattr(asset, "asset_tag", None),
                        "name": getattr(asset, "name", None),
                    }
                }
            
            elif action == "delete":
                if not asset_id:
                    return _error("MISSING_PARAMETER", "asset_id is required for delete action")
                
                client.assets.delete(asset_id)
                
                return {
                    "success": True,
                    "action": "delete",
                    "asset_id": asset_id,
                    "message": "Asset deleted successfully"
                }
            
    except SnipeITNotFoundError as e:
        logger.error(f"Asset not found: {e}")
        return _error("NOT_FOUND", f"Asset not found: {str(e)}")
    except SnipeITAuthenticationError as e:
        logger.error(f"Authentication error: {e}")
        return _error("AUTHENTICATION_FAILED", f"Authentication failed: {str(e)}")
    except SnipeITValidationError as e:
        logger.error(f"Validation error: {e}")
        return _snipeit_validation_error(e)
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return _error("API_ERROR", f"Snipe-IT error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in manage_assets: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
)
def asset_operations(
    action: Annotated[
        Literal["checkout", "checkin", "audit", "restore"],
        "The operation to perform on the asset"
    ],
    asset_id: Annotated[int, "Asset ID"],
    checkout_data: Annotated[CheckoutData | None, "Checkout details (required for checkout action)"] = None,
    checkin_data: Annotated[CheckinData | None, "Checkin details (optional for checkin action)"] = None,
    audit_data: Annotated[AuditData | None, "Audit details (optional for audit action)"] = None,
) -> dict[str, Any]:
    """Perform state operations on assets (checkout, checkin, audit, restore).
    
    Operations:
    - checkout: Check out an asset to a user, location, or another asset
    - checkin: Check in an asset back to inventory
    - audit: Mark an asset as audited
    - restore: Restore a soft-deleted asset
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        client = get_snipeit_client()
        
        with client:
            asset = client.assets.get(asset_id)
            
            if action == "checkout":
                if not checkout_data:
                    return _error("MISSING_PARAMETER", "checkout_data is required for checkout action")
                
                # Build checkout kwargs
                checkout_kwargs = {
                    "checkout_to_type": checkout_data.checkout_to_type,
                    "assigned_to_id": checkout_data.assigned_to_id,
                }
                
                if checkout_data.expected_checkin:
                    checkout_kwargs["expected_checkin"] = checkout_data.expected_checkin
                if checkout_data.checkout_at:
                    checkout_kwargs["checkout_at"] = checkout_data.checkout_at
                if checkout_data.note:
                    checkout_kwargs["note"] = checkout_data.note
                if checkout_data.name:
                    checkout_kwargs["name"] = checkout_data.name
                
                updated_asset = asset.checkout(**checkout_kwargs)
                
                return {
                    "success": True,
                    "action": "checkout",
                    "asset_id": asset_id,
                    "message": f"Asset checked out to {checkout_data.checkout_to_type} {checkout_data.assigned_to_id}",
                    "asset": {
                        "id": updated_asset.id,
                        "asset_tag": getattr(updated_asset, "asset_tag", None),
                        "assigned_to": getattr(updated_asset, "assigned_to", None),
                    }
                }
            
            elif action == "checkin":
                checkin_kwargs = {}
                if checkin_data:
                    if checkin_data.note:
                        checkin_kwargs["note"] = checkin_data.note
                    if checkin_data.location_id:
                        checkin_kwargs["location_id"] = checkin_data.location_id
                
                updated_asset = asset.checkin(**checkin_kwargs)
                
                return {
                    "success": True,
                    "action": "checkin",
                    "asset_id": asset_id,
                    "message": "Asset checked in successfully",
                    "asset": {
                        "id": updated_asset.id,
                        "asset_tag": getattr(updated_asset, "asset_tag", None),
                    }
                }
            
            elif action == "audit":
                audit_kwargs = {}
                if audit_data:
                    if audit_data.location_id:
                        audit_kwargs["location_id"] = audit_data.location_id
                    if audit_data.note:
                        audit_kwargs["note"] = audit_data.note
                    if audit_data.next_audit_date:
                        audit_kwargs["next_audit_date"] = audit_data.next_audit_date
                
                updated_asset = asset.audit(**audit_kwargs)
                
                return {
                    "success": True,
                    "action": "audit",
                    "asset_id": asset_id,
                    "message": "Asset audited successfully",
                    "asset": {
                        "id": updated_asset.id,
                        "asset_tag": getattr(updated_asset, "asset_tag", None),
                    }
                }
            
            elif action == "restore":
                updated_asset = asset.restore()
                
                return {
                    "success": True,
                    "action": "restore",
                    "asset_id": asset_id,
                    "message": "Asset restored successfully",
                    "asset": {
                        "id": updated_asset.id,
                        "asset_tag": getattr(updated_asset, "asset_tag", None),
                    }
                }
    
    except SnipeITNotFoundError as e:
        logger.error(f"Asset not found: {e}")
        return _error("NOT_FOUND", f"Asset not found: {str(e)}")
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return _error("API_ERROR", f"Snipe-IT error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in asset_operations: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
    }
)
def asset_files(
    action: Annotated[
        Literal["upload", "list", "download", "delete"],
        "The file operation to perform"
    ],
    asset_id: Annotated[int, "Asset ID"],
    file_paths: Annotated[list[str] | None, "List of file paths to upload (for upload action)"] = None,
    notes: Annotated[str | None, "Notes for uploaded files (for upload action)"] = None,
    file_id: Annotated[int | None, "File ID (required for download and delete actions)"] = None,
    save_path: Annotated[str | None, "Path to save downloaded file (for download action)"] = None,
) -> dict[str, Any]:
    """Manage file attachments for assets.
    
    Operations:
    - upload: Upload one or more files to an asset
    - list: List all files attached to an asset
    - download: Download a specific file from an asset
    - delete: Delete a specific file from an asset
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "upload":
                if not file_paths:
                    return _error("MISSING_PARAMETER", "file_paths is required for upload action")
                
                result = client.assets.upload_files(asset_id, file_paths, notes)
                
                return {
                    "success": True,
                    "action": "upload",
                    "asset_id": asset_id,
                    "message": f"Uploaded {len(file_paths)} file(s) successfully",
                    "result": result
                }
            
            elif action == "list":
                result = client.assets.list_files(asset_id)
                
                return {
                    "success": True,
                    "action": "list",
                    "asset_id": asset_id,
                    "files": result
                }
            
            elif action == "download":
                if file_id is None:
                    return _error("MISSING_PARAMETER", "file_id is required for download action")
                if not save_path:
                    return _error("MISSING_PARAMETER", "save_path is required for download action")
                
                downloaded_path = client.assets.download_file(asset_id, file_id, save_path)
                
                return {
                    "success": True,
                    "action": "download",
                    "asset_id": asset_id,
                    "file_id": file_id,
                    "saved_to": downloaded_path,
                    "message": f"File downloaded to {downloaded_path}"
                }
            
            elif action == "delete":
                if file_id is None:
                    return _error("MISSING_PARAMETER", "file_id is required for delete action")
                
                client.assets.delete_file(asset_id, file_id)
                
                return {
                    "success": True,
                    "action": "delete",
                    "asset_id": asset_id,
                    "file_id": file_id,
                    "message": "File deleted successfully"
                }
    
    except SnipeITNotFoundError as e:
        logger.error(f"Asset or file not found: {e}")
        return _error("NOT_FOUND", f"Not found: {str(e)}")
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return _error("API_ERROR", f"Snipe-IT error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in asset_files: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
)
def asset_labels(
    asset_ids: Annotated[list[int] | None, "List of asset IDs to generate labels for"] = None,
    asset_tags: Annotated[list[str] | None, "List of asset tags to generate labels for"] = None,
    save_path: Annotated[str, "Path where the PDF labels file should be saved"] = "/tmp/asset_labels.pdf",
) -> dict[str, Any]:
    """Generate printable labels for assets.
    
    Provide either asset_ids or asset_tags to generate labels for specific assets.
    The labels will be saved as a PDF file to the specified save_path.
    
    Returns:
        dict: Result with path to generated labels PDF
    """
    try:
        client = get_snipeit_client()
        
        if not asset_ids and not asset_tags:
            return _error("MISSING_PARAMETER", "Either asset_ids or asset_tags must be provided")
        
        with client:
            # If asset_ids provided, get the Asset objects
            if asset_ids:
                assets = [client.assets.get(asset_id) for asset_id in asset_ids]
                saved_path = client.assets.labels(save_path, assets)
            else:
                # Use asset_tags directly
                saved_path = client.assets.labels(save_path, asset_tags)
            
            return {
                "success": True,
                "action": "generate_labels",
                "saved_to": saved_path,
                "message": f"Labels generated and saved to {saved_path}"
            }
    
    except SnipeITNotFoundError as e:
        logger.error(f"Asset not found: {e}")
        return _error("NOT_FOUND", f"Asset not found: {str(e)}")
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return _error("API_ERROR", f"Snipe-IT error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in asset_labels: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
)
def asset_maintenance(
    action: Annotated[
        Literal["create"],
        "The maintenance operation to perform (currently only create is supported)"
    ],
    asset_id: Annotated[int, "Asset ID"],
    maintenance_data: Annotated[MaintenanceData, "Maintenance record data (required for create action)"],
) -> dict[str, Any]:
    """Manage maintenance records for assets.
    
    Currently supports:
    - create: Create a new maintenance record for an asset
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                # Build maintenance payload
                maintenance_kwargs = {
                    "asset_id": asset_id,
                    "asset_improvement": maintenance_data.asset_improvement,
                    "supplier_id": maintenance_data.supplier_id,
                    "title": maintenance_data.title,
                }
                
                if maintenance_data.cost is not None:
                    maintenance_kwargs["cost"] = maintenance_data.cost
                if maintenance_data.start_date:
                    maintenance_kwargs["start_date"] = maintenance_data.start_date
                if maintenance_data.completion_date:
                    maintenance_kwargs["completion_date"] = maintenance_data.completion_date
                if maintenance_data.notes:
                    maintenance_kwargs["notes"] = maintenance_data.notes
                
                result = client.assets.create_maintenance(**maintenance_kwargs)
                
                return {
                    "success": True,
                    "action": "create",
                    "asset_id": asset_id,
                    "message": "Maintenance record created successfully",
                    "maintenance": result
                }
    
    except SnipeITNotFoundError as e:
        logger.error(f"Asset not found: {e}")
        return _error("NOT_FOUND", f"Asset not found: {str(e)}")
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return _error("API_ERROR", f"Snipe-IT error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in asset_maintenance: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
def asset_licenses(
    asset_id: Annotated[int, "Asset ID"],
) -> dict[str, Any]:
    """Get all licenses checked out to an asset.
    
    Returns:
        dict: List of licenses associated with the asset
    """
    try:
        client = get_snipeit_client()
        
        with client:
            result = client.assets.get_licenses(asset_id)
            
            return {
                "success": True,
                "asset_id": asset_id,
                "licenses": result
            }
    
    except SnipeITNotFoundError as e:
        logger.error(f"Asset not found: {e}")
        return _error("NOT_FOUND", f"Asset not found: {str(e)}")
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return _error("API_ERROR", f"Snipe-IT error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in asset_licenses: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Consumable Tools
# ============================================================================

@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
    }
)
def manage_consumables(
    action: Annotated[
        Literal["create", "get", "list", "update", "delete"],
        "The action to perform on consumables"
    ],
    consumable_id: Annotated[int | None, "Consumable ID (required for get, update, delete)"] = None,
    consumable_data: Annotated[ConsumableData | None, "Consumable data (required for create, optional for update)"] = None,
    limit: Annotated[int | None, "Number of results to return (for list action)"] = 50,
    offset: Annotated[int | None, "Number of results to skip (for list action)"] = 0,
    search: Annotated[str | None, "Search query (for list action)"] = None,
    sort: Annotated[str | None, "Field to sort by (for list action)"] = None,
    order: Annotated[Literal["asc", "desc"] | None, "Sort order (for list action)"] = None,
) -> dict[str, Any]:
    """Manage Snipe-IT consumables with CRUD operations.
    
    This tool handles all basic consumable operations:
    - create: Create a new consumable (requires consumable_data with name, qty, and category_id)
    - get: Retrieve a single consumable by ID
    - list: List consumables with optional pagination and filtering
    - update: Update an existing consumable (requires consumable_id and consumable_data)
    - delete: Delete a consumable (requires consumable_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not consumable_data:
                    return _error("MISSING_PARAMETER", "consumable_data is required for create action")
                
                if not consumable_data.name or consumable_data.qty is None or not consumable_data.category_id:
                    return _error("MISSING_PARAMETER", "name, qty, and category_id are required to create a consumable")
                
                # Build creation payload
                create_kwargs = {k: v for k, v in consumable_data.model_dump().items() if v is not None}
                consumable = client.consumables.create(**create_kwargs)
                
                return {
                    "success": True,
                    "action": "create",
                    "consumable": {
                        "id": consumable.id,
                        "name": getattr(consumable, "name", None),
                        "qty": getattr(consumable, "qty", None),
                    }
                }
            
            elif action == "get":
                if not consumable_id:
                    return _error("MISSING_PARAMETER", "consumable_id is required for get action")
                
                consumable = client.consumables.get(consumable_id)
                
                # Extract consumable data
                consumable_dict = {
                    "id": consumable.id,
                    "name": getattr(consumable, "name", None),
                    "qty": getattr(consumable, "qty", None),
                    "category": getattr(consumable, "category", None),
                    "company": getattr(consumable, "company", None),
                    "location": getattr(consumable, "location", None),
                    "manufacturer": getattr(consumable, "manufacturer", None),
                    "model_number": getattr(consumable, "model_number", None),
                    "item_no": getattr(consumable, "item_no", None),
                    "order_number": getattr(consumable, "order_number", None),
                    "purchase_date": getattr(consumable, "purchase_date", None),
                    "purchase_cost": getattr(consumable, "purchase_cost", None),
                    "min_amt": getattr(consumable, "min_amt", None),
                    "remaining": getattr(consumable, "remaining", None),
                }
                
                return {
                    "success": True,
                    "action": "get",
                    "consumable": consumable_dict
                }
            
            elif action == "list":
                params = {"limit": limit, "offset": offset}
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                consumables = client.consumables.list(**params)
                
                consumables_list = [
                    {
                        "id": consumable.id,
                        "name": getattr(consumable, "name", None),
                        "qty": getattr(consumable, "qty", None),
                        "remaining": getattr(consumable, "remaining", None),
                    }
                    for consumable in consumables
                ]
                
                return {
                    "success": True,
                    "action": "list",
                    "count": len(consumables_list),
                    "consumables": consumables_list
                }
            
            elif action == "update":
                if not consumable_id:
                    return _error("MISSING_PARAMETER", "consumable_id is required for update action")
                if not consumable_data:
                    return _error("MISSING_PARAMETER", "consumable_data is required for update action")
                
                # Build update payload (only include non-None values)
                update_kwargs = {k: v for k, v in consumable_data.model_dump().items() if v is not None}
                
                consumable = client.consumables.patch(consumable_id, **update_kwargs)
                
                return {
                    "success": True,
                    "action": "update",
                    "consumable": {
                        "id": consumable.id,
                        "name": getattr(consumable, "name", None),
                        "qty": getattr(consumable, "qty", None),
                    }
                }
            
            elif action == "delete":
                if not consumable_id:
                    return _error("MISSING_PARAMETER", "consumable_id is required for delete action")
                
                client.consumables.delete(consumable_id)
                
                return {
                    "success": True,
                    "action": "delete",
                    "consumable_id": consumable_id,
                    "message": "Consumable deleted successfully"
                }
    
    except SnipeITNotFoundError as e:
        logger.error(f"Consumable not found: {e}")
        return _error("NOT_FOUND", f"Consumable not found: {str(e)}")
    except SnipeITAuthenticationError as e:
        logger.error(f"Authentication error: {e}")
        return _error("AUTHENTICATION_FAILED", f"Authentication failed: {str(e)}")
    except SnipeITValidationError as e:
        logger.error(f"Validation error: {e}")
        return _snipeit_validation_error(e)
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return _error("API_ERROR", f"Snipe-IT error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in manage_consumables: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Label Import Tools
#
# The caller (an LLM with vision) reads the NTUST label photo itself and passes the
# extracted fields directly — no server-side OCR pipeline is involved.
# ============================================================================

@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
)
def import_asset_from_label(
    label_data: Annotated[LabelAssetData, "Asset fields read directly off the label photo"],
    status_id: Annotated[int, "Status label ID (required for asset creation)"],
    model_id: Annotated[int, "Asset model ID (required for asset creation)"],
    location_id: Annotated[int | None, "Location ID (optional)"] = None,
    preview_only: Annotated[bool, "If True, return the asset payload without creating it"] = False,
) -> dict[str, Any]:
    """Create a Snipe-IT asset from an NTUST label photo you've already read with vision.

    Look at the label image yourself, fill in `label_data` with what you see (converting
    ROC dates and year-based lifespans as described on each field), then call this tool.
    Use preview_only=True to review the payload before committing to asset creation.

    Returns:
        dict: The asset creation result (or payload preview if preview_only=True)
    """
    try:
        asset_data = AssetData(
            status_id=status_id,
            model_id=model_id,
            asset_tag=label_data.asset_tag,
            name=label_data.name,
            serial=label_data.serial,
            purchase_date=label_data.purchase_date,
            warranty_months=label_data.warranty_months,
            location_id=location_id,
            notes=f"Imported from label. Specs: {label_data.specs or 'N/A'}\n"
                  f"Custodian Unit: {label_data.custodian_unit or 'N/A'}\n"
                  f"Custodian: {label_data.custodian or 'N/A'}\n"
                  f"Funding: {label_data.funding_source or 'N/A'}"
        )
        create_kwargs = {k: v for k, v in asset_data.model_dump().items() if v is not None}

        if preview_only:
            return {
                "success": True,
                "preview_mode": True,
                "asset_payload": create_kwargs,
                "message": "Payload built successfully. Set preview_only=False to create asset."
            }

        client = get_snipeit_client()

        with client:
            asset = client.hardware.create(**create_kwargs)

            return {
                "success": True,
                "asset": {
                    "id": asset.id,
                    "asset_tag": getattr(asset, "asset_tag", None),
                    "name": getattr(asset, "name", None),
                    "serial": getattr(asset, "serial", None),
                },
                "message": f"Asset created successfully with ID: {asset.id}"
            }

    except SnipeITValidationError as e:
        logger.error(f"Validation error: {e}")
        return _snipeit_validation_error(e, prefix="Asset creation failed")
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return _error("API_ERROR", f"Snipe-IT error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in import_asset_from_label: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Import failed: {str(e)}")


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
)
def batch_import_labels(
    items: Annotated[list[LabelAssetData], "Asset fields read directly off each label photo, one entry per asset"],
    status_id: Annotated[int, "Status label ID for all assets"],
    model_id: Annotated[int, "Asset model ID for all assets"],
    location_id: Annotated[int | None, "Location ID for all assets (optional)"] = None,
    stop_on_error: Annotated[bool, "Stop processing on first error"] = False,
) -> dict[str, Any]:
    """Batch-create assets from multiple NTUST label photos you've already read with vision.

    Look at each label image yourself and build one `LabelAssetData` entry per asset in
    `items`, then call this tool. Returns a summary of successes and failures.

    Returns:
        dict: Summary with success_count, failure_count, and detailed results
    """
    results = []
    success_count = 0
    failure_count = 0

    for i, label_data in enumerate(items, 1):
        logger.info(f"Processing label {i}/{len(items)}")

        result = import_asset_from_label(
            label_data=label_data,
            status_id=status_id,
            model_id=model_id,
            location_id=location_id,
            preview_only=False
        )

        if result.get("success"):
            success_count += 1
        else:
            failure_count += 1
            if stop_on_error:
                logger.warning(f"Stopping batch import due to error on item {i}")
                break

        results.append({
            "index": i,
            "result": result
        })

    return {
        "success": True,
        "total": len(items),
        "processed": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
        "results": results
    }


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
def get_asset_qr_code(
    asset_id: Annotated[int | None, "Asset ID"] = None,
    asset_tag: Annotated[str | None, "Asset tag"] = None,
    save_path: Annotated[str, "Path to save the QR code image"] = "/tmp/qr_code.png",
    code_type: Annotated[Literal["qr", "barcode"], "Type of code to generate"] = "qr",
) -> dict[str, Any]:
    """Get individual QR code or barcode image for an asset.
    
    Fetches the QR code (2D) or barcode (1D) PNG image from Snipe-IT and saves it
    to the specified path. This is separate from PDF label generation.
    
    Args:
        asset_id: Asset ID (provide either asset_id or asset_tag)
        asset_tag: Asset tag (provide either asset_id or asset_tag)
        save_path: Path to save the image file
        code_type: "qr" for 2D QR code, "barcode" for 1D barcode
    
    Returns:
        dict: Success status and path to saved image
    """
    try:
        if not asset_id and not asset_tag:
            return _error("MISSING_PARAMETER", "Either asset_id or asset_tag must be provided")
        
        client = get_snipeit_client()
        
        # If asset_tag provided, get asset_id first
        if asset_tag and not asset_id:
            with client:
                assets = client.hardware.list(search=asset_tag, limit=1)
                if not assets:
                    return _error("NOT_FOUND", f"Asset not found with tag: {asset_tag}")
                asset_id = assets[0].id
        
        # Build URL based on code type
        if code_type == "qr":
            url = f"{SNIPEIT_URL}/hardware/{asset_id}/qr_code"
        else:  # barcode
            url = f"{SNIPEIT_URL}/hardware/{asset_id}/barcode"
        
        # Fetch image
        import requests
        headers = {
            "Authorization": f"Bearer {SNIPEIT_TOKEN}",
            "Accept": "image/png"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Save image
        output_path = Path(save_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        
        return {
            "success": True,
            "asset_id": asset_id,
            "code_type": code_type,
            "saved_to": str(output_path),
            "file_size": len(response.content)
        }
    
    except requests.HTTPError as e:
        logger.error(f"HTTP error fetching {code_type}: {e}")
        return _error("API_ERROR", f"Failed to fetch {code_type}: {str(e)}")
    except Exception as e:
        logger.error(f"Error in get_asset_qr_code: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Failed to get {code_type}: {str(e)}")



# ============================================================================
# Accessories Management
# ============================================================================

@mcp.tool(
    description="""Manage Snipe-IT accessories with CRUD operations.
    
    This tool handles all basic accessory operations:
    - create: Create a new accessory (requires accessory_data with at least name, qty, and category_id)
    - get: Retrieve a single accessory by ID
    - list: List accessories with optional pagination and filtering
    - update: Update an existing accessory (requires accessory_id and accessory_data)
    - delete: Delete an accessory (requires accessory_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def manage_accessories(
    action: Literal["create", "get", "list", "update", "delete"],
    accessory_id: int | None = None,
    accessory_data: AccessoryData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None
) -> dict[str, Any]:
    """Manage accessories in Snipe-IT."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not accessory_data:
                    return _error("MISSING_PARAMETER", "accessory_data is required for create action")
                
                data = accessory_data.model_dump(exclude_none=True)
                accessory = client.accessories.create(**data)
                return {
                    "success": True,
                    "data": {
                        "id": accessory.id,
                        "name": getattr(accessory, "name", None),
                    },
                    "message": f"Accessory created successfully with ID: {accessory.id}"
                }
            
            elif action == "get":
                if not accessory_id:
                    return _error("MISSING_PARAMETER", "accessory_id is required for get action")
                
                accessory = client.accessories.get(accessory_id)
                return {"success": True, "data": accessory}
            
            elif action == "list":
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                accessories = client.accessories.list(**params)
                return {"success": True, "data": accessories, "count": len(accessories)}
            
            elif action == "update":
                if not accessory_id:
                    return _error("MISSING_PARAMETER", "accessory_id is required for update action")
                if not accessory_data:
                    return _error("MISSING_PARAMETER", "accessory_data is required for update action")
                
                data = accessory_data.model_dump(exclude_none=True)
                accessory = client.accessories.update(accessory_id, **data)
                return {
                    "success": True,
                    "data": accessory,
                    "message": f"Accessory {accessory_id} updated successfully"
                }
            
            elif action == "delete":
                if not accessory_id:
                    return _error("MISSING_PARAMETER", "accessory_id is required for delete action")
                
                client.accessories.delete(accessory_id)
                return {
                    "success": True,
                    "message": f"Accessory {accessory_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_accessories: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_accessories: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool(
    description="""Perform operations on accessories (checkout, checkin, history).
    
    Operations:
    - checkout: Check out an accessory to a user
    - checkin: Check in an accessory
    - history: Get accessory action history
    - checkedout: List checked out items
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def accessory_operations(
    action: Literal["checkout", "checkin", "history", "checkedout"],
    accessory_id: int,
    assigned_to: int | None = None,
    note: str | None = None
) -> dict[str, Any]:
    """Perform checkout/checkin/history operations on accessories."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "checkout":
                if not assigned_to:
                    return _error("MISSING_PARAMETER", "assigned_to (user_id) is required for checkout")
                
                params = {"assigned_to": assigned_to}
                if note:
                    params["note"] = note
                
                result = client.accessories.checkout(accessory_id, **params)
                return {
                    "success": True,
                    "data": result,
                    "message": f"Accessory {accessory_id} checked out successfully"
                }
            
            elif action == "checkin":
                result = client.accessories.checkin(accessory_id)
                return {
                    "success": True,
                    "data": result,
                    "message": f"Accessory {accessory_id} checked in successfully"
                }
            
            elif action == "history":
                history = client.accessories.history(accessory_id)
                return {"success": True, "data": history}
            
            elif action == "checkedout":
                checkedout = client.accessories.checkedout(accessory_id)
                return {"success": True, "data": checkedout}
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in accessory_operations: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in accessory_operations: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Categories Management
# ============================================================================

@mcp.tool(
    description="""Manage Snipe-IT categories with CRUD operations.
    
    Operations:
    - create: Create a new category (requires category_data with name and category_type;
      category_type must be one of: asset, accessory, consumable, component, license)
    - get: Retrieve a single category by ID
    - list: List categories with optional pagination and filtering
    - update: Update an existing category (requires category_id and category_data)
    - delete: Delete a category (requires category_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def manage_categories(
    action: Literal["create", "get", "list", "update", "delete"],
    category_id: int | None = None,
    category_data: CategoryData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None
) -> dict[str, Any]:
    """Manage categories in Snipe-IT."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not category_data:
                    return _error("MISSING_PARAMETER", "category_data is required for create action")
                
                data = category_data.model_dump(exclude_none=True)
                category = client.categories.create(**data)
                return {
                    "success": True,
                    "data": {
                        "id": category.id,
                        "name": getattr(category, "name", None),
                    },
                    "message": f"Category created successfully with ID: {category.id}"
                }
            
            elif action == "get":
                if not category_id:
                    return _error("MISSING_PARAMETER", "category_id is required for get action")
                
                category = client.categories.get(category_id)
                return {"success": True, "data": category}
            
            elif action == "list":
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                categories = client.categories.list(**params)
                return {"success": True, "data": categories, "count": len(categories)}
            
            elif action == "update":
                if not category_id:
                    return _error("MISSING_PARAMETER", "category_id is required for update action")
                if not category_data:
                    return _error("MISSING_PARAMETER", "category_data is required for update action")
                
                data = category_data.model_dump(exclude_none=True)
                category = client.categories.update(category_id, **data)
                return {
                    "success": True,
                    "data": category,
                    "message": f"Category {category_id} updated successfully"
                }
            
            elif action == "delete":
                if not category_id:
                    return _error("MISSING_PARAMETER", "category_id is required for delete action")
                
                client.categories.delete(category_id)
                return {
                    "success": True,
                    "message": f"Category {category_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_categories: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_categories: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Companies Management
# ============================================================================

@mcp.tool(
    description="""Manage Snipe-IT companies with CRUD operations.
    
    Operations:
    - create: Create a new company (requires company_data with name)
    - get: Retrieve a single company by ID
    - list: List companies with optional pagination and filtering
    - update: Update an existing company (requires company_id and company_data)
    - delete: Delete a company (requires company_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def manage_companies(
    action: Literal["create", "get", "list", "update", "delete"],
    company_id: int | None = None,
    company_data: CompanyData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None
) -> dict[str, Any]:
    """Manage companies in Snipe-IT."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not company_data:
                    return _error("MISSING_PARAMETER", "company_data is required for create action")
                
                data = company_data.model_dump(exclude_none=True)
                company = client.companies.create(**data)
                return {
                    "success": True,
                    "data": {
                        "id": company.id,
                        "name": getattr(company, "name", None),
                    },
                    "message": f"Company created successfully with ID: {company.id}"
                }
            
            elif action == "get":
                if not company_id:
                    return _error("MISSING_PARAMETER", "company_id is required for get action")
                
                company = client.companies.get(company_id)
                return {"success": True, "data": company}
            
            elif action == "list":
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                companies = client.companies.list(**params)
                return {"success": True, "data": companies, "count": len(companies)}
            
            elif action == "update":
                if not company_id:
                    return _error("MISSING_PARAMETER", "company_id is required for update action")
                if not company_data:
                    return _error("MISSING_PARAMETER", "company_data is required for update action")
                
                data = company_data.model_dump(exclude_none=True)
                company = client.companies.update(company_id, **data)
                return {
                    "success": True,
                    "data": company,
                    "message": f"Company {company_id} updated successfully"
                }
            
            elif action == "delete":
                if not company_id:
                    return _error("MISSING_PARAMETER", "company_id is required for delete action")
                
                client.companies.delete(company_id)
                return {
                    "success": True,
                    "message": f"Company {company_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_companies: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_companies: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Licenses Management
# ============================================================================

@mcp.tool(
    description="""Manage Snipe-IT licenses with CRUD operations.
    
    Operations:
    - create: Create a new license (requires license_data with name, seats, and category_id)
    - get: Retrieve a single license by ID
    - list: List licenses with optional pagination and filtering
    - update: Update an existing license (requires license_id and license_data)
    - delete: Delete a license (requires license_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def manage_licenses(
    action: Literal["create", "get", "list", "update", "delete"],
    license_id: int | None = None,
    license_data: LicenseData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None
) -> dict[str, Any]:
    """Manage licenses in Snipe-IT."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not license_data:
                    return _error("MISSING_PARAMETER", "license_data is required for create action")
                
                data = license_data.model_dump(exclude_none=True)
                license = client.licenses.create(**data)
                return {
                    "success": True,
                    "data": {
                        "id": license.id,
                        "name": getattr(license, "name", None),
                    },
                    "message": f"License created successfully with ID: {license.id}"
                }
            
            elif action == "get":
                if not license_id:
                    return _error("MISSING_PARAMETER", "license_id is required for get action")
                
                license = client.licenses.get(license_id)
                return {"success": True, "data": license}
            
            elif action == "list":
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                licenses = client.licenses.list(**params)
                return {"success": True, "data": licenses, "count": len(licenses)}
            
            elif action == "update":
                if not license_id:
                    return _error("MISSING_PARAMETER", "license_id is required for update action")
                if not license_data:
                    return _error("MISSING_PARAMETER", "license_data is required for update action")
                
                data = license_data.model_dump(exclude_none=True)
                license = client.licenses.update(license_id, **data)
                return {
                    "success": True,
                    "data": license,
                    "message": f"License {license_id} updated successfully"
                }
            
            elif action == "delete":
                if not license_id:
                    return _error("MISSING_PARAMETER", "license_id is required for delete action")
                
                client.licenses.delete(license_id)
                return {
                    "success": True,
                    "message": f"License {license_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_licenses: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_licenses: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool(
    description="""Perform operations on license seats (checkout, checkin).
    
    Operations:
    - checkout: Check out a license seat to a user or asset
    - checkin: Check in a license seat
    - seats: List all seats for a license
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def license_seats_operations(
    action: Literal["checkout", "checkin", "seats"],
    license_id: int,
    seat_id: int | None = None,
    assigned_to: int | None = None,
    asset_id: int | None = None,
    note: str | None = None
) -> dict[str, Any]:
    """Perform checkout/checkin operations on license seats."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "checkout":
                if not assigned_to:
                    return _error("MISSING_PARAMETER", "assigned_to (user_id) is required for checkout")
                
                params = {"assigned_to": assigned_to}
                if asset_id:
                    params["asset_id"] = asset_id
                if note:
                    params["note"] = note
                
                result = client.licenses.checkout(license_id, **params)
                return {
                    "success": True,
                    "data": result,
                    "message": f"License {license_id} seat checked out successfully"
                }
            
            elif action == "checkin":
                if not seat_id:
                    return _error("MISSING_PARAMETER", "seat_id is required for checkin")
                
                result = client.licenses.checkin(license_id, seat_id)
                return {
                    "success": True,
                    "data": result,
                    "message": f"License seat {seat_id} checked in successfully"
                }
            
            elif action == "seats":
                seats = client.licenses.seats(license_id)
                return {"success": True, "data": seats}
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in license_seats_operations: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in license_seats_operations: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Locations Management
# ============================================================================

@mcp.tool(
    description="""Manage Snipe-IT locations with CRUD operations.
    
    Operations:
    - create: Create a new location (requires location_data with name)
    - get: Retrieve a single location by ID
    - list: List locations with optional pagination and filtering
    - update: Update an existing location (requires location_id and location_data)
    - delete: Delete a location (requires location_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def manage_locations(
    action: Literal["create", "get", "list", "update", "delete"],
    location_id: int | None = None,
    location_data: LocationData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None
) -> dict[str, Any]:
    """Manage locations in Snipe-IT."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not location_data:
                    return _error("MISSING_PARAMETER", "location_data is required for create action")
                
                data = location_data.model_dump(exclude_none=True)
                location = client.locations.create(**data)
                return {
                    "success": True,
                    "data": {
                        "id": location.id,
                        "name": getattr(location, "name", None),
                    },
                    "message": f"Location created successfully with ID: {location.id}"
                }
            
            elif action == "get":
                if not location_id:
                    return _error("MISSING_PARAMETER", "location_id is required for get action")
                
                location = client.locations.get(location_id)
                return {"success": True, "data": location}
            
            elif action == "list":
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                locations = client.locations.list(**params)
                return {"success": True, "data": locations, "count": len(locations)}
            
            elif action == "update":
                if not location_id:
                    return _error("MISSING_PARAMETER", "location_id is required for update action")
                if not location_data:
                    return _error("MISSING_PARAMETER", "location_data is required for update action")
                
                data = location_data.model_dump(exclude_none=True)
                location = client.locations.update(location_id, **data)
                return {
                    "success": True,
                    "data": location,
                    "message": f"Location {location_id} updated successfully"
                }
            
            elif action == "delete":
                if not location_id:
                    return _error("MISSING_PARAMETER", "location_id is required for delete action")
                
                client.locations.delete(location_id)
                return {
                    "success": True,
                    "message": f"Location {location_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_locations: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_locations: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Manufacturers Management
# ============================================================================

@mcp.tool(
    description="""Manage Snipe-IT manufacturers with CRUD operations.
    
    Operations:
    - create: Create a new manufacturer (requires manufacturer_data with name)
    - get: Retrieve a single manufacturer by ID
    - list: List manufacturers with optional pagination and filtering
    - update: Update an existing manufacturer (requires manufacturer_id and manufacturer_data)
    - delete: Delete a manufacturer (requires manufacturer_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def manage_manufacturers(
    action: Literal["create", "get", "list", "update", "delete"],
    manufacturer_id: int | None = None,
    manufacturer_data: ManufacturerData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None
) -> dict[str, Any]:
    """Manage manufacturers in Snipe-IT."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not manufacturer_data:
                    return _error("MISSING_PARAMETER", "manufacturer_data is required for create action")
                
                data = manufacturer_data.model_dump(exclude_none=True)
                manufacturer = client.manufacturers.create(**data)
                return {
                    "success": True,
                    "data": {
                        "id": manufacturer.id,
                        "name": getattr(manufacturer, "name", None),
                    },
                    "message": f"Manufacturer created successfully with ID: {manufacturer.id}"
                }
            
            elif action == "get":
                if not manufacturer_id:
                    return _error("MISSING_PARAMETER", "manufacturer_id is required for get action")
                
                manufacturer = client.manufacturers.get(manufacturer_id)
                return {"success": True, "data": manufacturer}
            
            elif action == "list":
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                manufacturers = client.manufacturers.list(**params)
                return {"success": True, "data": manufacturers, "count": len(manufacturers)}
            
            elif action == "update":
                if not manufacturer_id:
                    return _error("MISSING_PARAMETER", "manufacturer_id is required for update action")
                if not manufacturer_data:
                    return _error("MISSING_PARAMETER", "manufacturer_data is required for update action")
                
                data = manufacturer_data.model_dump(exclude_none=True)
                manufacturer = client.manufacturers.update(manufacturer_id, **data)
                return {
                    "success": True,
                    "data": manufacturer,
                    "message": f"Manufacturer {manufacturer_id} updated successfully"
                }
            
            elif action == "delete":
                if not manufacturer_id:
                    return _error("MISSING_PARAMETER", "manufacturer_id is required for delete action")
                
                client.manufacturers.delete(manufacturer_id)
                return {
                    "success": True,
                    "message": f"Manufacturer {manufacturer_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_manufacturers: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_manufacturers: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Models Management
# ============================================================================

@mcp.tool(
    description="""Manage Snipe-IT asset models with CRUD operations.
    
    Operations:
    - create: Create a new model (requires model_data with name, category_id, and manufacturer_id)
    - get: Retrieve a single model by ID
    - list: List models with optional pagination and filtering
    - update: Update an existing model (requires model_id and model_data)
    - delete: Delete a model (requires model_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def manage_models(
    action: Literal["create", "get", "list", "update", "delete"],
    model_id: int | None = None,
    model_data: ModelData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None
) -> dict[str, Any]:
    """Manage asset models in Snipe-IT."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not model_data:
                    return _error("MISSING_PARAMETER", "model_data is required for create action")
                
                data = model_data.model_dump(exclude_none=True)
                model = client.models.create(**data)
                return {
                    "success": True,
                    "data": {
                        "id": model.id,
                        "name": getattr(model, "name", None),
                    },
                    "message": f"Model created successfully with ID: {model.id}"
                }
            
            elif action == "get":
                if not model_id:
                    return _error("MISSING_PARAMETER", "model_id is required for get action")
                
                model = client.models.get(model_id)
                return {"success": True, "data": model}
            
            elif action == "list":
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                models = client.models.list(**params)
                return {"success": True, "data": models, "count": len(models)}
            
            elif action == "update":
                if not model_id:
                    return _error("MISSING_PARAMETER", "model_id is required for update action")
                if not model_data:
                    return _error("MISSING_PARAMETER", "model_data is required for update action")
                
                data = model_data.model_dump(exclude_none=True)
                model = client.models.update(model_id, **data)
                return {
                    "success": True,
                    "data": model,
                    "message": f"Model {model_id} updated successfully"
                }
            
            elif action == "delete":
                if not model_id:
                    return _error("MISSING_PARAMETER", "model_id is required for delete action")
                
                client.models.delete(model_id)
                return {
                    "success": True,
                    "message": f"Model {model_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_models: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_models: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Status Labels Management
# ============================================================================

@mcp.tool(
    description="""Manage Snipe-IT status labels with CRUD operations.
    
    Operations:
    - create: Create a new status label (requires status_data with name and type;
      type must be one of: deployable, pending, undeployable, archived)
    - get: Retrieve a single status label by ID
    - list: List status labels with optional pagination and filtering
    - update: Update an existing status label (requires status_id and status_data)
    - delete: Delete a status label (requires status_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def manage_status_labels(
    action: Literal["create", "get", "list", "update", "delete"],
    status_id: int | None = None,
    status_data: StatusLabelData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None
) -> dict[str, Any]:
    """Manage status labels in Snipe-IT."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not status_data:
                    return _error("MISSING_PARAMETER", "status_data is required for create action")
                
                data = status_data.model_dump(exclude_none=True)
                status = client.status_labels.create(**data)
                return {
                    "success": True,
                    "data": {
                        "id": status.id,
                        "name": getattr(status, "name", None),
                    },
                    "message": f"Status label created successfully with ID: {status.id}"
                }
            
            elif action == "get":
                if not status_id:
                    return _error("MISSING_PARAMETER", "status_id is required for get action")
                
                status = client.status_labels.get(status_id)
                return {"success": True, "data": status}
            
            elif action == "list":
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                statuses = client.status_labels.list(**params)
                return {"success": True, "data": statuses, "count": len(statuses)}
            
            elif action == "update":
                if not status_id:
                    return _error("MISSING_PARAMETER", "status_id is required for update action")
                if not status_data:
                    return _error("MISSING_PARAMETER", "status_data is required for update action")
                
                data = status_data.model_dump(exclude_none=True)
                status = client.status_labels.update(status_id, **data)
                return {
                    "success": True,
                    "data": status,
                    "message": f"Status label {status_id} updated successfully"
                }
            
            elif action == "delete":
                if not status_id:
                    return _error("MISSING_PARAMETER", "status_id is required for delete action")
                
                client.status_labels.delete(status_id)
                return {
                    "success": True,
                    "message": f"Status label {status_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_status_labels: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_status_labels: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Suppliers Management
# ============================================================================

@mcp.tool(
    description="""Manage Snipe-IT suppliers with CRUD operations.
    
    Operations:
    - create: Create a new supplier (requires supplier_data with name)
    - get: Retrieve a single supplier by ID
    - list: List suppliers with optional pagination and filtering
    - update: Update an existing supplier (requires supplier_id and supplier_data)
    - delete: Delete a supplier (requires supplier_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
)
def manage_suppliers(
    action: Literal["create", "get", "list", "update", "delete"],
    supplier_id: int | None = None,
    supplier_data: SupplierData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None
) -> dict[str, Any]:
    """Manage suppliers in Snipe-IT."""
    try:
        client = get_snipeit_client()
        
        with client:
            if action == "create":
                if not supplier_data:
                    return _error("MISSING_PARAMETER", "supplier_data is required for create action")
                
                data = supplier_data.model_dump(exclude_none=True)
                supplier = client.suppliers.create(**data)
                return {
                    "success": True,
                    "data": {
                        "id": supplier.id,
                        "name": getattr(supplier, "name", None),
                    },
                    "message": f"Supplier created successfully with ID: {supplier.id}"
                }
            
            elif action == "get":
                if not supplier_id:
                    return _error("MISSING_PARAMETER", "supplier_id is required for get action")
                
                supplier = client.suppliers.get(supplier_id)
                return {"success": True, "data": supplier}
            
            elif action == "list":
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                suppliers = client.suppliers.list(**params)
                return {"success": True, "data": suppliers, "count": len(suppliers)}
            
            elif action == "update":
                if not supplier_id:
                    return _error("MISSING_PARAMETER", "supplier_id is required for update action")
                if not supplier_data:
                    return _error("MISSING_PARAMETER", "supplier_data is required for update action")
                
                data = supplier_data.model_dump(exclude_none=True)
                supplier = client.suppliers.update(supplier_id, **data)
                return {
                    "success": True,
                    "data": supplier,
                    "message": f"Supplier {supplier_id} updated successfully"
                }
            
            elif action == "delete":
                if not supplier_id:
                    return _error("MISSING_PARAMETER", "supplier_id is required for delete action")
                
                client.suppliers.delete(supplier_id)
                return {
                    "success": True,
                    "message": f"Supplier {supplier_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_suppliers: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_suppliers: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Users Management
# ============================================================================

def _prepare_user_payload(user_data: UserData, *, require_create: bool = False) -> dict[str, Any] | dict[str, str]:
    """Dump UserData and enforce Snipe-IT create rules. Returns payload or error dict."""
    data = user_data.model_dump(exclude_none=True)
    if data.get("password") and not data.get("password_confirmation"):
        data["password_confirmation"] = data["password"]

    if require_create:
        missing: list[str] = []
        if not data.get("first_name"):
            missing.append("first_name")
        ldap = bool(data.get("ldap_import"))
        if not ldap and not data.get("username"):
            missing.append("username")
        if not ldap and not data.get("password"):
            missing.append("password")
        if missing:
            return _error("MISSING_PARAMETER", f"Missing required fields for create: {', '.join(missing)}")
    return data


@mcp.tool(
    description="""Manage Snipe-IT users (CRUD + nested ops).

    Operations:
    - create: New user (user_data: first_name, username, password required unless ldap_import;
      password_confirmation auto-filled if omitted)
    - get / list / update / delete: standard CRUD
    - restore: Soft-deleted user (user_id)
    - selectlist: Dropdown list (search/limit/offset)
    - assets / accessories / licenses / history: items assigned to user (user_id)
    - email_inventory: Email user their assigned assets (user_id)
    - two_factor_reset: Reset 2FA for user (user_id)
    - ldap_sync: Run LDAP user sync (optional location_id)

    Returns:
        dict: success status and data/error
    """
)
def manage_users(
    action: Literal[
        "create",
        "get",
        "list",
        "update",
        "delete",
        "restore",
        "selectlist",
        "assets",
        "accessories",
        "licenses",
        "history",
        "email_inventory",
        "two_factor_reset",
        "ldap_sync",
    ],
    user_id: int | None = None,
    user_data: UserData | None = None,
    limit: int | None = 50,
    offset: int | None = 0,
    search: str | None = None,
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None,
    location_id: int | None = None,
) -> dict[str, Any]:
    """Manage users in Snipe-IT."""
    try:
        client = get_snipeit_client()

        with client:
            if action == "create":
                if not user_data:
                    return _error("MISSING_PARAMETER", "user_data is required for create action")

                prepared = _prepare_user_payload(user_data, require_create=True)
                if prepared.get("success") is False:
                    return prepared  # type: ignore[return-value]
                data = prepared

                username = data.pop("username", None)
                if not username and not data.get("ldap_import"):
                    return _error("MISSING_PARAMETER", "username is required for create action")

                if username:
                    user = client.users.create(username=username, **data)
                else:
                    user = client.users.create(username="", **data)

                return {
                    "success": True,
                    "data": {
                        "id": user.id,
                        "username": getattr(user, "username", None),
                        "first_name": getattr(user, "first_name", None),
                        "last_name": getattr(user, "last_name", None),
                        "email": getattr(user, "email", None),
                        "name": getattr(user, "name", None),
                    },
                    "message": f"User created successfully with ID: {user.id}",
                }

            elif action == "get":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for get action")

                user = client.users.get(user_id)
                return {"success": True, "data": user}

            elif action == "list":
                params: dict[str, Any] = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order

                users = client.users.list(**params)
                return {"success": True, "data": users, "count": len(users)}

            elif action == "update":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for update action")
                if not user_data:
                    return _error("MISSING_PARAMETER", "user_data is required for update action")

                data = _prepare_user_payload(user_data, require_create=False)
                user = client.users.update(user_id, **data)
                return {
                    "success": True,
                    "data": user,
                    "message": f"User {user_id} updated successfully",
                }

            elif action == "delete":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for delete action")

                client.users.delete(user_id)
                return {
                    "success": True,
                    "message": f"User {user_id} deleted successfully",
                }

            elif action == "restore":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for restore action")
                result = client._request("POST", f"users/{user_id}/restore")
                return {"success": True, "data": result, "message": f"User {user_id} restored successfully"}

            elif action == "selectlist":
                params = {}
                if search:
                    params["search"] = search
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                result = client._request("GET", "users/selectlist", params=params or None)
                return {"success": True, "data": result}

            elif action == "assets":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for assets action")
                result = client._request("GET", f"users/{user_id}/assets")
                return {"success": True, "data": result}

            elif action == "accessories":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for accessories action")
                result = client._request("GET", f"users/{user_id}/accessories")
                return {"success": True, "data": result}

            elif action == "licenses":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for licenses action")
                result = client._request("GET", f"users/{user_id}/licenses")
                return {"success": True, "data": result}

            elif action == "history":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for history action")
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                result = client._request("GET", f"users/{user_id}/history", params=params or None)
                return {"success": True, "data": result}

            elif action == "email_inventory":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for email_inventory action")
                result = client._request("POST", f"users/{user_id}/email")
                return {"success": True, "data": result}

            elif action == "two_factor_reset":
                if not user_id:
                    return _error("MISSING_PARAMETER", "user_id is required for two_factor_reset action")
                result = client._request("POST", "users/two_factor_reset", json={"id": user_id})
                return {"success": True, "data": result}

            elif action == "ldap_sync":
                payload: dict[str, Any] = {}
                if location_id is not None:
                    payload["location_id"] = location_id
                result = client._request("POST", "users/ldapsync", json=payload)
                return {"success": True, "data": result}

            return _error("INVALID_ACTION", f"Unknown action: {action}")

    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_users: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_users: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def manage_components(
    action: Literal["create", "get", "list", "update", "delete"],
    component_id: Optional[int] = None,
    component_data: Optional[ComponentData] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    order: Optional[Literal["asc", "desc"]] = None
) -> dict:
    """
    Manage Snipe-IT components with CRUD operations.
    
    This tool handles all basic component operations:
    - create: Create a new component (requires component_data with name, qty, and category_id)
    - get: Retrieve a single component by ID
    - list: List components with optional pagination and filtering
    - update: Update an existing component (requires component_id and component_data)
    - delete: Delete a component (requires component_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "create":
                if not component_data:
                    return _error("MISSING_PARAMETER", "component_data is required for create action")
                
                payload = {k: v for k, v in component_data.model_dump().items() if v is not None}
                result = snipe.components.create(**payload)
                return {"success": True, "data": result}
            
            elif action == "get":
                if not component_id:
                    return _error("MISSING_PARAMETER", "component_id is required for get action")
                
                result = snipe.components.get(component_id)
                return {"success": True, "data": result}
            
            elif action == "list":
                params = {"limit": limit, "offset": offset}
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                result = snipe.components.list(**params)
                return {"success": True, "data": result}
            
            elif action == "update":
                if not component_id:
                    return _error("MISSING_PARAMETER", "component_id is required for update action")
                if not component_data:
                    return _error("MISSING_PARAMETER", "component_data is required for update action")
                
                payload = {k: v for k, v in component_data.model_dump().items() if v is not None}
                result = snipe.components.update(component_id, **payload)
                return {"success": True, "data": result}
            
            elif action == "delete":
                if not component_id:
                    return _error("MISSING_PARAMETER", "component_id is required for delete action")
                
                snipe.components.delete(component_id)
                return {
                    "success": True,
                    "message": f"Component {component_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_components: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_components: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def component_operations(
    action: Literal["checkout", "checkin"],
    component_id: int,
    asset_id: Optional[int] = None,
    assigned_qty: Optional[int] = None,
    note: Optional[str] = None
) -> dict:
    """
    Perform checkout and checkin operations on components.
    
    Operations:
    - checkout: Check out component to an asset (requires asset_id and assigned_qty)
    - checkin: Check in component from an asset (requires asset_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "checkout":
                if not asset_id:
                    return _error("MISSING_PARAMETER", "asset_id is required for checkout")
                if not assigned_qty:
                    return _error("MISSING_PARAMETER", "assigned_qty is required for checkout")
                
                payload = {
                    "assigned_asset": asset_id,
                    "assigned_qty": assigned_qty
                }
                if note:
                    payload["note"] = note
                
                # Use raw HTTP request since library doesn't implement checkout for components
                result = snipe._request("POST", f"components/{component_id}/checkout", json=payload)
                return {"success": True, "data": result}
            
            elif action == "checkin":
                if not asset_id:
                    return _error("MISSING_PARAMETER", "asset_id is required for checkin")
                
                payload = {"asset_id": asset_id}
                if note:
                    payload["note"] = note
                
                # Use raw HTTP request since library doesn't implement checkin for components
                result = snipe._request("POST", f"components/{component_id}/checkin", json=payload)
                return {"success": True, "data": result}
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in component_operations: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in component_operations: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def manage_departments(
    action: Literal["create", "get", "list", "update", "delete"],
    department_id: Optional[int] = None,
    department_data: Optional[DepartmentData] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    order: Optional[Literal["asc", "desc"]] = None
) -> dict:
    """
    Manage Snipe-IT departments with CRUD operations.
    
    This tool handles all basic department operations:
    - create: Create a new department (requires department_data with name)
    - get: Retrieve a single department by ID
    - list: List departments with optional pagination and filtering
    - update: Update an existing department (requires department_id and department_data)
    - delete: Delete a department (requires department_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "create":
                if not department_data:
                    return _error("MISSING_PARAMETER", "department_data is required for create action")
                
                payload = {k: v for k, v in department_data.model_dump().items() if v is not None}
                result = snipe.departments.create(**payload)
                return {"success": True, "data": result}
            
            elif action == "get":
                if not department_id:
                    return _error("MISSING_PARAMETER", "department_id is required for get action")
                
                result = snipe.departments.get(department_id)
                return {"success": True, "data": result}
            
            elif action == "list":
                params = {"limit": limit, "offset": offset}
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                result = snipe.departments.get(**params)
                return {"success": True, "data": result}
            
            elif action == "update":
                if not department_id:
                    return _error("MISSING_PARAMETER", "department_id is required for update action")
                if not department_data:
                    return _error("MISSING_PARAMETER", "department_data is required for update action")
                
                payload = {k: v for k, v in department_data.model_dump().items() if v is not None}
                result = snipe.departments.update(department_id, **payload)
                return {"success": True, "data": result}
            
            elif action == "delete":
                if not department_id:
                    return _error("MISSING_PARAMETER", "department_id is required for delete action")
                
                snipe.departments.delete(department_id)
                return {
                    "success": True,
                    "message": f"Department {department_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_departments: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_departments: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def manage_custom_fields(
    action: Literal["create", "get", "list", "update", "delete"],
    field_id: Optional[int] = None,
    field_data: Optional[CustomFieldData] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    order: Optional[Literal["asc", "desc"]] = None
) -> dict:
    """
    Manage Snipe-IT custom fields with CRUD operations.
    
    This tool handles all basic custom field operations:
    - create: Create a new custom field (requires field_data with name and element;
      element must be one of: text, listbox, textarea, markdown-textarea, checkbox, radio)
    - get: Retrieve a single custom field by ID
    - list: List custom fields with optional pagination and filtering
    - update: Update an existing custom field (requires field_id and field_data)
    - delete: Delete a custom field (requires field_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "create":
                if not field_data:
                    return _error("MISSING_PARAMETER", "field_data is required for create action")
                
                payload = {k: v for k, v in field_data.model_dump().items() if v is not None}
                result = snipe.fields.create(**payload)
                return {"success": True, "data": result}
            
            elif action == "get":
                if not field_id:
                    return _error("MISSING_PARAMETER", "field_id is required for get action")
                
                result = snipe.fields.get(field_id)
                return {"success": True, "data": result}
            
            elif action == "list":
                params = {"limit": limit, "offset": offset}
                if search:
                    params["search"] = search
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                result = snipe.fields.get(**params)
                return {"success": True, "data": result}
            
            elif action == "update":
                if not field_id:
                    return _error("MISSING_PARAMETER", "field_id is required for update action")
                if not field_data:
                    return _error("MISSING_PARAMETER", "field_data is required for update action")
                
                payload = {k: v for k, v in field_data.model_dump().items() if v is not None}
                result = snipe.fields.update(field_id, **payload)
                return {"success": True, "data": result}
            
            elif action == "delete":
                if not field_id:
                    return _error("MISSING_PARAMETER", "field_id is required for delete action")
                
                snipe.fields.delete(field_id)
                return {
                    "success": True,
                    "message": f"Custom field {field_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_custom_fields: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_custom_fields: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def manage_fieldsets(
    action: Literal["create", "get", "list", "update", "delete"],
    fieldset_id: Optional[int] = None,
    fieldset_data: Optional[FieldsetData] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    sort: Optional[str] = None,
    order: Optional[Literal["asc", "desc"]] = None
) -> dict:
    """
    Manage Snipe-IT fieldsets with CRUD operations.
    
    This tool handles all basic fieldset operations:
    - create: Create a new fieldset (requires fieldset_data with name)
    - get: Retrieve a single fieldset by ID
    - list: List fieldsets with optional pagination
    - update: Update an existing fieldset (requires fieldset_id and fieldset_data)
    - delete: Delete a fieldset (requires fieldset_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "create":
                if not fieldset_data:
                    return _error("MISSING_PARAMETER", "fieldset_data is required for create action")
                
                payload = {k: v for k, v in fieldset_data.model_dump().items() if v is not None}
                result = snipe.fieldsets.create(**payload)
                return {"success": True, "data": result}
            
            elif action == "get":
                if not fieldset_id:
                    return _error("MISSING_PARAMETER", "fieldset_id is required for get action")
                
                result = snipe.fieldsets.get(fieldset_id)
                return {"success": True, "data": result}
            
            elif action == "list":
                params = {"limit": limit, "offset": offset}
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                result = snipe.fieldsets.get(**params)
                return {"success": True, "data": result}
            
            elif action == "update":
                if not fieldset_id:
                    return _error("MISSING_PARAMETER", "fieldset_id is required for update action")
                if not fieldset_data:
                    return _error("MISSING_PARAMETER", "fieldset_data is required for update action")
                
                payload = {k: v for k, v in fieldset_data.model_dump().items() if v is not None}
                result = snipe.fieldsets.update(fieldset_id, **payload)
                return {"success": True, "data": result}
            
            elif action == "delete":
                if not fieldset_id:
                    return _error("MISSING_PARAMETER", "fieldset_id is required for delete action")
                
                snipe.fieldsets.delete(fieldset_id)
                return {
                    "success": True,
                    "message": f"Fieldset {fieldset_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_fieldsets: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_fieldsets: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def fieldset_field_operations(
    action: Literal["associate", "disassociate"],
    fieldset_id: int,
    field_id: int,
    order: Optional[int] = None,
    required: Optional[bool] = None
) -> dict:
    """
    Associate or disassociate custom fields with fieldsets.
    
    Operations:
    - associate: Add a custom field to a fieldset (optional: order, required)
    - disassociate: Remove a custom field from a fieldset
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "associate":
                payload = {"field_id": field_id}
                if order is not None:
                    payload["order"] = order
                if required is not None:
                    payload["required"] = required
                
                result = snipe.fieldsets.associate_field(fieldset_id, **payload)
                return {"success": True, "data": result}
            
            elif action == "disassociate":
                result = snipe.fieldsets.disassociate_field(fieldset_id, field_id)
                return {"success": True, "data": result}
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in fieldset_field_operations: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in fieldset_field_operations: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# DISABLED: Groups endpoint not available in snipeit-python-api library
@mcp.tool()
async def manage_groups(
    action: Literal["create", "get", "list", "update", "delete"],
    group_id: Optional[int] = None,
    group_data: Optional[GroupData] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    sort: Optional[str] = None,
    order: Optional[Literal["asc", "desc"]] = None
) -> dict:
    """
    Manage Snipe-IT groups (user groups/permissions) with CRUD operations.
    
    This tool handles all basic group operations:
    - create: Create a new group (requires group_data with name)
    - get: Retrieve a single group by ID
    - list: List groups with optional pagination
    - update: Update an existing group (requires group_id and group_data)
    - delete: Delete a group (requires group_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "create":
                if not group_data:
                    return _error("MISSING_PARAMETER", "group_data is required for create action")
                
                payload = {k: v for k, v in group_data.model_dump().items() if v is not None}
                result = snipe._request("POST", "groups", json=payload)
                return {"success": True, "data": result}
            
            elif action == "get":
                if not group_id:
                    return _error("MISSING_PARAMETER", "group_id is required for get action")
                
                result = snipe._request("GET", f"groups/{group_id}")
                return {"success": True, "data": result}
            
            elif action == "list":
                params = {"limit": limit, "offset": offset}
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                result = snipe._request("GET", "groups", params=params)
                return {"success": True, "data": result}
            
            elif action == "update":
                if not group_id:
                    return _error("MISSING_PARAMETER", "group_id is required for update action")
                if not group_data:
                    return _error("MISSING_PARAMETER", "group_data is required for update action")
                
                payload = {k: v for k, v in group_data.model_dump().items() if v is not None}
                result = snipe._request("PUT", f"groups/{group_id}", json=payload)
                return {"success": True, "data": result}
            
            elif action == "delete":
                if not group_id:
                    return _error("MISSING_PARAMETER", "group_id is required for delete action")
                
                snipe._request("DELETE", f"groups/{group_id}")
                return {
                    "success": True,
                    "message": f"Group {group_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_groups: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_groups: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def account_profile(
    action: Literal["me", "requests", "requestable_assets"]
) -> dict:
    """
    Access account and profile information for the authenticated user.

    Operations:
    - me: GET /users/me — current user profile
    - requests: GET /account/requests — assets requested by current user
    - requestable_assets: GET /account/requestable/hardware — requestable assets

    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "me":
                result = snipe.users.me()
                return {"success": True, "data": result}

            elif action == "requests":
                result = snipe._request("GET", "account/requests")
                return {"success": True, "data": result}

            elif action == "requestable_assets":
                result = snipe._request("GET", "account/requestable/hardware")
                return {"success": True, "data": result}

            return _error("INVALID_ACTION", f"Unknown action: {action}")

    except SnipeITException as e:
        logger.error(f"Snipe-IT error in account_profile: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in account_profile: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def lookup_assets(
    action: Literal["by_serial", "by_tag"],
    value: str
) -> dict:
    """
    Look up assets by serial number or asset tag.
    
    Operations:
    - by_serial: Find asset by serial number
    - by_tag: Find asset by asset tag
    
    Args:
        value: Serial number or asset tag to look up
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "by_serial":
                result = snipe.assets.search(search=value, search_in_serial=True)
                return {"success": True, "data": result}
            
            elif action == "by_tag":
                result = snipe.assets.search(search=value, search_in_asset_tag=True)
                return {"success": True, "data": result}
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in lookup_assets: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in lookup_assets: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def checkout_by_tag(
    asset_tag: str,
    checkout_to_type: Literal["user", "asset", "location"],
    assigned_to_id: int,
    checkout_at: Optional[str] = None,
    expected_checkin: Optional[str] = None,
    note: Optional[str] = None,
    name: Optional[str] = None
) -> dict:
    """
    Check out an asset by its asset tag (convenience method).
    
    Args:
        asset_tag: Asset tag of the asset to checkout
        checkout_to_type: Type of entity to checkout to (user, asset, or location)
        assigned_to_id: ID of the user/asset/location
        checkout_at: Checkout date (YYYY-MM-DD)
        expected_checkin: Expected checkin date (YYYY-MM-DD)
        note: Checkout notes
        name: Name for the checkout
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            # First, look up the asset by tag
            search_result = snipe.assets.search(search=asset_tag, search_in_asset_tag=True)
            
            if not search_result or not search_result.get("rows"):
                return _error("NOT_FOUND", f"Asset with tag '{asset_tag}' not found")
            
            asset_id = search_result["rows"][0]["id"]
            
            # Then checkout the asset
            payload = {
                "checkout_to_type": checkout_to_type,
                "assigned_to": assigned_to_id
            }
            if checkout_at:
                payload["checkout_at"] = checkout_at
            if expected_checkin:
                payload["expected_checkin"] = expected_checkin
            if note:
                payload["note"] = note
            if name:
                payload["name"] = name
            
            result = snipe.assets.checkout(asset_id, **payload)
            return {"success": True, "data": result, "asset_id": asset_id}
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in checkout_by_tag: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in checkout_by_tag: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def manage_depreciations(
    action: Literal["create", "get", "list", "update", "delete"],
    depreciation_id: Optional[int] = None,
    depreciation_data: Optional[DepreciationData] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    sort: Optional[str] = None,
    order: Optional[Literal["asc", "desc"]] = None
) -> dict:
    """
    Manage Snipe-IT depreciations with CRUD operations.
    
    This tool handles all basic depreciation operations:
    - create: Create a new depreciation (requires depreciation_data with name and months)
    - get: Retrieve a single depreciation by ID
    - list: List depreciations with optional pagination
    - update: Update an existing depreciation (requires depreciation_id and depreciation_data)
    - delete: Delete a depreciation (requires depreciation_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "create":
                if not depreciation_data:
                    return _error("MISSING_PARAMETER", "depreciation_data is required for create action")
                
                payload = {k: v for k, v in depreciation_data.model_dump().items() if v is not None}
                result = snipe._request("POST", "depreciations", json=payload)
                return {"success": True, "data": result}
            
            elif action == "get":
                if not depreciation_id:
                    return _error("MISSING_PARAMETER", "depreciation_id is required for get action")
                
                result = snipe._request("GET", f"depreciations/{depreciation_id}")
                return {"success": True, "data": result}
            
            elif action == "list":
                params = {"limit": limit, "offset": offset}
                if sort:
                    params["sort"] = sort
                if order:
                    params["order"] = order
                
                result = snipe._request("GET", "depreciations", params=params)
                return {"success": True, "data": result}
            
            elif action == "update":
                if not depreciation_id:
                    return _error("MISSING_PARAMETER", "depreciation_id is required for update action")
                if not depreciation_data:
                    return _error("MISSING_PARAMETER", "depreciation_data is required for update action")
                
                payload = {k: v for k, v in depreciation_data.model_dump().items() if v is not None}
                result = snipe._request("PUT", f"depreciations/{depreciation_id}", json=payload)
                return {"success": True, "data": result}
            
            elif action == "delete":
                if not depreciation_id:
                    return _error("MISSING_PARAMETER", "depreciation_id is required for delete action")
                
                snipe._request("DELETE", f"depreciations/{depreciation_id}")
                return {
                    "success": True,
                    "message": f"Depreciation {depreciation_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_depreciations: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_depreciations: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def manage_kits(
    action: Literal["create", "get", "list", "update", "delete"],
    kit_id: Optional[int] = None,
    kit_data: Optional[KitData] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0
) -> dict:
    """
    Manage Snipe-IT predefined kits with CRUD operations.
    
    This tool handles all basic kit operations:
    - create: Create a new kit (requires kit_data with name)
    - get: Retrieve a single kit by ID
    - list: List kits with optional pagination
    - update: Update an existing kit (requires kit_id and kit_data)
    - delete: Delete a kit (requires kit_id)
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "create":
                if not kit_data:
                    return _error("MISSING_PARAMETER", "kit_data is required for create action")
                
                payload = {k: v for k, v in kit_data.model_dump().items() if v is not None}
                result = snipe._request("POST", "kits", json=payload)
                return {"success": True, "data": result}
            
            elif action == "get":
                if not kit_id:
                    return _error("MISSING_PARAMETER", "kit_id is required for get action")
                
                result = snipe._request("GET", f"kits/{kit_id}")
                return {"success": True, "data": result}
            
            elif action == "list":
                params = {"limit": limit, "offset": offset}
                result = snipe._request("GET", "kits", params=params)
                return {"success": True, "data": result}
            
            elif action == "update":
                if not kit_id:
                    return _error("MISSING_PARAMETER", "kit_id is required for update action")
                if not kit_data:
                    return _error("MISSING_PARAMETER", "kit_data is required for update action")
                
                payload = {k: v for k, v in kit_data.model_dump().items() if v is not None}
                result = snipe._request("PUT", f"kits/{kit_id}", json=payload)
                return {"success": True, "data": result}
            
            elif action == "delete":
                if not kit_id:
                    return _error("MISSING_PARAMETER", "kit_id is required for delete action")
                
                snipe._request("DELETE", f"kits/{kit_id}")
                return {
                    "success": True,
                    "message": f"Kit {kit_id} deleted successfully"
                }
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in manage_kits: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in manage_kits: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def reports(
    action: Literal["activity", "depreciation"]
) -> dict:
    """
    Generate Snipe-IT reports.
    
    Operations:
    - activity: Get activity report
    - depreciation: Get depreciation report
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "activity":
                result = snipe._request("GET", "reports/activity")
                return {"success": True, "data": result}
            
            elif action == "depreciation":
                result = snipe._request("GET", "reports/depreciation")
                return {"success": True, "data": result}
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in reports: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in reports: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


@mcp.tool()
async def system_settings(
    action: Literal["get_settings", "ldap_test", "backup_list"]
) -> dict:
    """
    Access Snipe-IT system settings and utilities.
    
    Operations:
    - get_settings: Get system settings
    - ldap_test: Test LDAP connection
    - backup_list: List available backups
    
    Returns:
        dict: Result of the operation including success status and data
    """
    try:
        with get_snipeit_client() as snipe:
            if action == "get_settings":
                result = snipe._request("GET", "settings")
                return {"success": True, "data": result}
            
            elif action == "ldap_test":
                result = snipe._request("GET", "settings/ldaptest")
                return {"success": True, "data": result}
            
            elif action == "backup_list":
                result = snipe._request("GET", "settings/backups")
                return {"success": True, "data": result}
    
    except SnipeITException as e:
        logger.error(f"Snipe-IT error in system_settings: {e}")
        return _error("API_ERROR", str(e))
    except Exception as e:
        logger.error(f"Error in system_settings: {e}", exc_info=True)
        return _error("UNEXPECTED_ERROR", f"Unexpected error: {str(e)}")


# ============================================================================
# Server Entry Point
# ============================================================================

if __name__ == "__main__":
    # Run the server with stdio transport (default for MCP)
    mcp.run(transport="stdio")
