"""Snipe-IT MCP Server

A Model Context Protocol (MCP) server for managing Snipe-IT inventory.
Provides tools for CRUD operations on Assets and Consumables.
"""

import os
import logging
import re
from typing import Literal, Annotated, Any
from pathlib import Path
from pydantic import BaseModel, Field

from fastmcp import FastMCP
from snipeit import SnipeIT
from snipeit.exceptions import (
    SnipeITException,
    SnipeITNotFoundError,
    SnipeITAuthenticationError,
    SnipeITValidationError
)

# OCR imports (lazy-loaded to avoid startup failures if not installed)
try:
    from paddleocr import PaddleOCR
    from PIL import Image
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    logger.warning("PaddleOCR not available. Label extraction tools will not work.")

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
        description="Type of entity to checkout to"
    )
    assigned_to_id: int = Field(..., description="ID of the user/asset/location")
    expected_checkin: str | None = Field(None, description="Expected checkin date (YYYY-MM-DD)")
    checkout_at: str | None = Field(None, description="Checkout date (YYYY-MM-DD)")
    note: str | None = Field(None, description="Checkout notes")
    name: str | None = Field(None, description="Name for the checkout")


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


class LabelFieldMapping(BaseModel):
    """Model for configurable Chinese field names on NTUST labels."""
    asset_number: str = Field("財產編號", description="Asset number field name")
    acquisition_date: str = Field("取得日期", description="Acquisition date field name")
    serial_number: str = Field("序號", description="Serial number field name")
    lifespan: str = Field("年限", description="Lifespan field name")
    asset_name: str = Field("財產名稱", description="Asset name field name")
    custodian_unit: str = Field("保管單位", description="Custodian unit field name")
    custodian: str = Field("保管人員", description="Custodian field name")
    specs: str = Field("規格", description="Specifications field name")
    funding_source: str = Field("經費來源", description="Funding source field name")


class ExtractedLabelData(BaseModel):
    """Model for extracted label data from OCR."""
    asset_tag: str | None = Field(None, description="Extracted asset tag (財產編號)")
    serial: str | None = Field(None, description="Extracted serial number (序號)")
    name: str | None = Field(None, description="Extracted asset name (財產名稱)")
    purchase_date: str | None = Field(None, description="Extracted purchase date in YYYY-MM-DD format")
    warranty_months: int | None = Field(None, description="Extracted lifespan in months")
    specs: str | None = Field(None, description="Extracted specifications (規格)")
    custodian_unit: str | None = Field(None, description="Extracted custodian unit (保管單位)")
    custodian: str | None = Field(None, description="Extracted custodian name (保管人員)")
    funding_source: str | None = Field(None, description="Extracted funding source (經費來源)")
    raw_ocr_text: str = Field(..., description="Full OCR text for debugging")
    confidence: float | None = Field(None, description="Average OCR confidence score")


# ============================================================================
# Helper Functions for Label Extraction
# ============================================================================

def convert_roc_to_gregorian(roc_date: str) -> str | None:
    """
    Convert ROC (Republic of China) date to Gregorian date.
    
    ROC year + 1911 = Gregorian year
    Example: 107.07.06 -> 2018-07-06
    
    Args:
        roc_date: ROC date string (e.g., "107.07.06", "107-07-06", "107/07/06")
        
    Returns:
        Gregorian date in YYYY-MM-DD format, or None if parsing fails
    """
    try:
        # Remove whitespace
        roc_date = roc_date.strip()
        
        # Support multiple separators: . - /
        parts = re.split(r'[.\-/]', roc_date)
        if len(parts) != 3:
            logger.warning(f"Invalid ROC date format: {roc_date}")
            return None
        
        roc_year, month, day = parts
        
        # Convert to integers
        roc_year_int = int(roc_year)
        month_int = int(month)
        day_int = int(day)
        
        # Convert ROC year to Gregorian
        gregorian_year = roc_year_int + 1911
        
        # Format as YYYY-MM-DD
        return f"{gregorian_year:04d}-{month_int:02d}-{day_int:02d}"
        
    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to convert ROC date '{roc_date}': {e}")
        return None


def extract_field_value(ocr_text: str, field_name: str) -> str | None:
    """
    Extract value after a field name from OCR text.
    
    Looks for patterns like:
    - "財產編號: 3140101-03"
    - "財產編號：3140101-03" (full-width colon)
    - "財產編號 3140101-03" (space separator)
    
    Args:
        ocr_text: Full OCR text
        field_name: Chinese field name to search for
        
    Returns:
        Extracted value or None if not found
    """
    # Try multiple patterns
    patterns = [
        rf"{re.escape(field_name)}\s*[:：]\s*([^\n]+)",  # with colon
        rf"{re.escape(field_name)}\s+([^\n]+)",  # with space
    ]
    
    for pattern in patterns:
        match = re.search(pattern, ocr_text)
        if match:
            value = match.group(1).strip()
            # Remove common noise characters
            value = re.sub(r'[|]', '', value)
            return value if value else None
    
    return None


def parse_label_fields(ocr_text: str, field_mapping: LabelFieldMapping) -> dict[str, Any]:
    """
    Parse all fields from OCR text using field mapping.
    
    Args:
        ocr_text: Full OCR text from label
        field_mapping: Field name mapping for Chinese labels
        
    Returns:
        Dictionary of extracted fields
    """
    extracted = {}
    
    # Extract asset tag (財產編號)
    asset_tag = extract_field_value(ocr_text, field_mapping.asset_number)
    if asset_tag:
        extracted["asset_tag"] = asset_tag
    
    # Extract serial number (序號)
    serial = extract_field_value(ocr_text, field_mapping.serial_number)
    if serial:
        extracted["serial"] = serial
    
    # Extract asset name (財產名稱)
    name = extract_field_value(ocr_text, field_mapping.asset_name)
    if name:
        extracted["name"] = name
    
    # Extract acquisition date (取得日期) and convert ROC to Gregorian
    roc_date = extract_field_value(ocr_text, field_mapping.acquisition_date)
    if roc_date:
        gregorian_date = convert_roc_to_gregorian(roc_date)
        if gregorian_date:
            extracted["purchase_date"] = gregorian_date
    
    # Extract lifespan (年限) and convert years to months
    lifespan = extract_field_value(ocr_text, field_mapping.lifespan)
    if lifespan:
        try:
            years = int(re.search(r'\d+', lifespan).group())
            extracted["warranty_months"] = years * 12
        except (AttributeError, ValueError):
            logger.warning(f"Failed to parse lifespan: {lifespan}")
    
    # Extract specs (規格)
    specs = extract_field_value(ocr_text, field_mapping.specs)
    if specs:
        extracted["specs"] = specs
    
    # Extract custodian unit (保管單位)
    custodian_unit = extract_field_value(ocr_text, field_mapping.custodian_unit)
    if custodian_unit:
        extracted["custodian_unit"] = custodian_unit
    
    # Extract custodian (保管人員)
    custodian = extract_field_value(ocr_text, field_mapping.custodian)
    if custodian:
        extracted["custodian"] = custodian
    
    # Extract funding source (經費來源)
    funding_source = extract_field_value(ocr_text, field_mapping.funding_source)
    if funding_source:
        extracted["funding_source"] = funding_source
    
    return extracted


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
                    return {"success": False, "error": "asset_data is required for create action"}
                
                if not asset_data.status_id or not asset_data.model_id:
                    return {
                        "success": False,
                        "error": "status_id and model_id are required to create an asset"
                    }
                
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
                    return {
                        "success": False,
                        "error": "One of asset_id, asset_tag, or serial is required for get action"
                    }
                
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
                    return {"success": False, "error": "asset_id is required for update action"}
                if not asset_data:
                    return {"success": False, "error": "asset_data is required for update action"}
                
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
                    return {"success": False, "error": "asset_id is required for delete action"}
                
                client.assets.delete(asset_id)
                
                return {
                    "success": True,
                    "action": "delete",
                    "asset_id": asset_id,
                    "message": "Asset deleted successfully"
                }
            
    except SnipeITNotFoundError as e:
        logger.error(f"Asset not found: {e}")
        return {"success": False, "error": f"Asset not found: {str(e)}"}
    except SnipeITAuthenticationError as e:
        logger.error(f"Authentication error: {e}")
        return {"success": False, "error": f"Authentication failed: {str(e)}"}
    except SnipeITValidationError as e:
        logger.error(f"Validation error: {e}")
        return {"success": False, "error": f"Validation error: {str(e)}"}
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return {"success": False, "error": f"Snipe-IT error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in manage_assets: {e}", exc_info=True)
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


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
                    return {"success": False, "error": "checkout_data is required for checkout action"}
                
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
        return {"success": False, "error": f"Asset not found: {str(e)}"}
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return {"success": False, "error": f"Snipe-IT error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in asset_operations: {e}", exc_info=True)
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


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
                    return {"success": False, "error": "file_paths is required for upload action"}
                
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
                    return {"success": False, "error": "file_id is required for download action"}
                if not save_path:
                    return {"success": False, "error": "save_path is required for download action"}
                
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
                    return {"success": False, "error": "file_id is required for delete action"}
                
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
        return {"success": False, "error": f"Not found: {str(e)}"}
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return {"success": False, "error": f"Snipe-IT error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in asset_files: {e}", exc_info=True)
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


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
            return {
                "success": False,
                "error": "Either asset_ids or asset_tags must be provided"
            }
        
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
        return {"success": False, "error": f"Asset not found: {str(e)}"}
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return {"success": False, "error": f"Snipe-IT error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in asset_labels: {e}", exc_info=True)
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


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
        return {"success": False, "error": f"Asset not found: {str(e)}"}
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return {"success": False, "error": f"Snipe-IT error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in asset_maintenance: {e}", exc_info=True)
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


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
        return {"success": False, "error": f"Asset not found: {str(e)}"}
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return {"success": False, "error": f"Snipe-IT error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in asset_licenses: {e}", exc_info=True)
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


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
                    return {"success": False, "error": "consumable_data is required for create action"}
                
                if not consumable_data.name or consumable_data.qty is None or not consumable_data.category_id:
                    return {
                        "success": False,
                        "error": "name, qty, and category_id are required to create a consumable"
                    }
                
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
                    return {"success": False, "error": "consumable_id is required for get action"}
                
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
                    return {"success": False, "error": "consumable_id is required for update action"}
                if not consumable_data:
                    return {"success": False, "error": "consumable_data is required for update action"}
                
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
                    return {"success": False, "error": "consumable_id is required for delete action"}
                
                client.consumables.delete(consumable_id)
                
                return {
                    "success": True,
                    "action": "delete",
                    "consumable_id": consumable_id,
                    "message": "Consumable deleted successfully"
                }
    
    except SnipeITNotFoundError as e:
        logger.error(f"Consumable not found: {e}")
        return {"success": False, "error": f"Consumable not found: {str(e)}"}
    except SnipeITAuthenticationError as e:
        logger.error(f"Authentication error: {e}")
        return {"success": False, "error": f"Authentication failed: {str(e)}"}
    except SnipeITValidationError as e:
        logger.error(f"Validation error: {e}")
        return {"success": False, "error": f"Validation error: {str(e)}"}
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return {"success": False, "error": f"Snipe-IT error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in manage_consumables: {e}", exc_info=True)
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


# ============================================================================
# Label Extraction Tools
# ============================================================================

@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
def extract_label_data(
    image_path: Annotated[str, "Path to the label image file"],
    language: Annotated[str, "OCR language code (default: chinese_cht for Traditional Chinese)"] = "chinese_cht",
    field_mapping: Annotated[LabelFieldMapping | None, "Custom field name mapping for labels"] = None,
) -> dict[str, Any]:
    """Extract asset data from NTUST label photos using OCR.
    
    Uses PaddleOCR to extract text from Traditional Chinese labels and parse
    structured asset information including asset tag, serial number, purchase date,
    and other fields.
    
    Supports ROC (Republic of China) date conversion to Gregorian dates.
    
    Args:
        image_path: Path to the label image file (JPEG, PNG, etc.)
        language: OCR language code (default: "chinese_cht" for Traditional Chinese)
        field_mapping: Optional custom field names (defaults to NTUST standard fields)
    
    Returns:
        dict: Extracted label data with asset_tag, serial, name, purchase_date, etc.
    """
    if not PADDLEOCR_AVAILABLE:
        return {
            "success": False,
            "error": "PaddleOCR is not installed. Install dependencies with: uv sync"
        }
    
    try:
        # Validate image path
        image_file = Path(image_path)
        if not image_file.exists():
            return {"success": False, "error": f"Image file not found: {image_path}"}
        
        if not image_file.is_file():
            return {"success": False, "error": f"Path is not a file: {image_path}"}
        
        # Use default NTUST field mapping if not provided
        if field_mapping is None:
            field_mapping = LabelFieldMapping()
        
        logger.info(f"Initializing PaddleOCR with language: {language}")
        
        # Initialize PaddleOCR (use_angle_cls=True for better rotated text detection)
        ocr = PaddleOCR(
            use_angle_cls=True,
            lang=language,
            use_gpu=False,  # CPU-only for compatibility
            show_log=False
        )
        
        # Run OCR
        logger.info(f"Running OCR on image: {image_path}")
        result = ocr.ocr(str(image_file), cls=True)
        
        if not result or not result[0]:
            return {
                "success": False,
                "error": "No text detected in image"
            }
        
        # Extract text and confidence scores
        ocr_lines = []
        confidence_scores = []
        
        for line in result[0]:
            text = line[1][0]  # Extract text
            confidence = line[1][1]  # Extract confidence score
            ocr_lines.append(text)
            confidence_scores.append(confidence)
        
        # Combine all OCR text
        full_ocr_text = "\n".join(ocr_lines)
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        
        logger.info(f"OCR completed. Detected {len(ocr_lines)} lines with avg confidence: {avg_confidence:.2f}")
        
        # Parse fields from OCR text
        extracted_fields = parse_label_fields(full_ocr_text, field_mapping)
        
        # Build response
        extracted_data = ExtractedLabelData(
            asset_tag=extracted_fields.get("asset_tag"),
            serial=extracted_fields.get("serial"),
            name=extracted_fields.get("name"),
            purchase_date=extracted_fields.get("purchase_date"),
            warranty_months=extracted_fields.get("warranty_months"),
            specs=extracted_fields.get("specs"),
            custodian_unit=extracted_fields.get("custodian_unit"),
            custodian=extracted_fields.get("custodian"),
            funding_source=extracted_fields.get("funding_source"),
            raw_ocr_text=full_ocr_text,
            confidence=round(avg_confidence, 3)
        )
        
        return {
            "success": True,
            "extracted_data": extracted_data.model_dump(),
            "ocr_lines_count": len(ocr_lines)
        }
    
    except Exception as e:
        logger.error(f"Error in extract_label_data: {e}", exc_info=True)
        return {"success": False, "error": f"OCR extraction failed: {str(e)}"}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
)
def import_asset_from_label(
    image_path: Annotated[str, "Path to the label image file"],
    status_id: Annotated[int, "Status label ID (required for asset creation)"],
    model_id: Annotated[int, "Asset model ID (required for asset creation)"],
    location_id: Annotated[int | None, "Location ID (optional)"] = None,
    language: Annotated[str, "OCR language code"] = "chinese_cht",
    field_mapping: Annotated[LabelFieldMapping | None, "Custom field name mapping"] = None,
    preview_only: Annotated[bool, "If True, extract data without creating asset"] = False,
) -> dict[str, Any]:
    """Extract label data and create asset in Snipe-IT in one step.
    
    This workflow tool combines OCR extraction with asset creation. Use preview_only=True
    to review extracted data before committing to asset creation.
    
    Args:
        image_path: Path to the label image file
        status_id: Status label ID (required, e.g., 2 for "Ready to Deploy")
        model_id: Asset model ID (required)
        location_id: Location ID (optional)
        language: OCR language code (default: "chinese_cht")
        field_mapping: Custom field name mapping (optional)
        preview_only: If True, only extract and return data without creating asset
    
    Returns:
        dict: Extraction result and asset creation result (if preview_only=False)
    """
    try:
        # Step 1: Extract label data
        extraction_result = extract_label_data(
            image_path=image_path,
            language=language,
            field_mapping=field_mapping
        )
        
        if not extraction_result.get("success"):
            return extraction_result
        
        extracted_data = extraction_result["extracted_data"]
        
        # If preview only, return extracted data
        if preview_only:
            return {
                "success": True,
                "preview_mode": True,
                "extracted_data": extracted_data,
                "message": "Data extracted successfully. Set preview_only=False to create asset."
            }
        
        # Step 2: Create asset from extracted data
        asset_data = AssetData(
            status_id=status_id,
            model_id=model_id,
            asset_tag=extracted_data.get("asset_tag"),
            name=extracted_data.get("name"),
            serial=extracted_data.get("serial"),
            purchase_date=extracted_data.get("purchase_date"),
            warranty_months=extracted_data.get("warranty_months"),
            location_id=location_id,
            notes=f"Imported from label. Specs: {extracted_data.get('specs', 'N/A')}\n"
                  f"Custodian Unit: {extracted_data.get('custodian_unit', 'N/A')}\n"
                  f"Custodian: {extracted_data.get('custodian', 'N/A')}\n"
                  f"Funding: {extracted_data.get('funding_source', 'N/A')}"
        )
        
        # Create asset using existing manage_assets tool logic
        client = get_snipeit_client()
        
        with client:
            # Build creation payload (only include non-None values)
            create_kwargs = {k: v for k, v in asset_data.model_dump().items() if v is not None}
            asset = client.hardware.create(**create_kwargs)
            
            return {
                "success": True,
                "extracted_data": extracted_data,
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
        return {
            "success": False,
            "error": f"Asset creation failed: {str(e)}",
            "extracted_data": extraction_result.get("extracted_data") if extraction_result.get("success") else None
        }
    except SnipeITException as e:
        logger.error(f"Snipe-IT error: {e}")
        return {
            "success": False,
            "error": f"Snipe-IT error: {str(e)}",
            "extracted_data": extraction_result.get("extracted_data") if extraction_result.get("success") else None
        }
    except Exception as e:
        logger.error(f"Unexpected error in import_asset_from_label: {e}", exc_info=True)
        return {"success": False, "error": f"Import failed: {str(e)}"}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
)
def batch_import_labels(
    image_paths: Annotated[list[str], "List of paths to label image files"],
    status_id: Annotated[int, "Status label ID for all assets"],
    model_id: Annotated[int, "Asset model ID for all assets"],
    location_id: Annotated[int | None, "Location ID for all assets (optional)"] = None,
    language: Annotated[str, "OCR language code"] = "chinese_cht",
    stop_on_error: Annotated[bool, "Stop processing on first error"] = False,
) -> dict[str, Any]:
    """Batch import multiple assets from label images.
    
    Processes multiple label images and creates assets for each one. Returns
    summary of successes and failures.
    
    Args:
        image_paths: List of paths to label image files
        status_id: Status label ID for all assets
        model_id: Asset model ID for all assets
        location_id: Location ID for all assets (optional)
        language: OCR language code (default: "chinese_cht")
        stop_on_error: If True, stop processing on first error
    
    Returns:
        dict: Summary with success_count, failure_count, and detailed results
    """
    results = []
    success_count = 0
    failure_count = 0
    
    for i, image_path in enumerate(image_paths, 1):
        logger.info(f"Processing label {i}/{len(image_paths)}: {image_path}")
        
        result = import_asset_from_label(
            image_path=image_path,
            status_id=status_id,
            model_id=model_id,
            location_id=location_id,
            language=language,
            preview_only=False
        )
        
        if result.get("success"):
            success_count += 1
        else:
            failure_count += 1
            if stop_on_error:
                logger.warning(f"Stopping batch import due to error on image {i}")
                break
        
        results.append({
            "image_path": image_path,
            "index": i,
            "result": result
        })
    
    return {
        "success": True,
        "total": len(image_paths),
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
            return {"success": False, "error": "Either asset_id or asset_tag must be provided"}
        
        client = get_snipeit_client()
        
        # If asset_tag provided, get asset_id first
        if asset_tag and not asset_id:
            with client:
                assets = client.hardware.list(search=asset_tag, limit=1)
                if not assets:
                    return {"success": False, "error": f"Asset not found with tag: {asset_tag}"}
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
        return {"success": False, "error": f"Failed to fetch {code_type}: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in get_asset_qr_code: {e}", exc_info=True)
        return {"success": False, "error": f"Failed to get {code_type}: {str(e)}"}


# ============================================================================
# Server Entry Point
# ============================================================================

if __name__ == "__main__":
    # Run the server with stdio transport (default for MCP)
    mcp.run(transport="stdio")
