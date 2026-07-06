# Snipe-IT MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for managing [Snipe-IT](https://snipeitapp.com/) inventory systems. This server provides AI assistants with tools to perform CRUD operations on assets and consumables in your Snipe-IT instance.

## Features

- **Comprehensive Asset Management**: Create, read, update, delete, and search assets
- **Asset Operations**: Checkout, checkin, audit, and restore assets
- **File Management**: Upload, download, list, and delete asset attachments
- **Label Generation**: Generate printable PDF labels for assets
- **OCR Label Extraction**: Extract asset data from NTUST label photos using Traditional Chinese OCR
- **QR Code Generation**: Generate individual QR code and barcode images for assets
- **Maintenance Tracking**: Create maintenance records for assets
- **License Management**: View licenses associated with assets
- **Consumable Management**: Full CRUD operations for consumables
- **ROC Date Conversion**: Automatic conversion of ROC (Republic of China) dates to Gregorian
- **Type-Safe**: Built with Pydantic models for robust validation
- **Error Handling**: Comprehensive error handling and logging

## Requirements

- Python 3.11 or higher
- [UV](https://github.com/astral-sh/uv) package manager
- A running Snipe-IT instance with API access
- Snipe-IT API token with appropriate permissions
- **For OCR features**: OpenCV system libraries (install with `brew install opencv` on macOS)

## Installation

### 1. Clone or download this repository

```bash
git clone <repository-url>
cd snipeit-mcp
```

### 2. Install dependencies using UV

```bash
# Install dependencies and create virtual environment
uv sync

# This will:
# - Create a virtual environment at .venv
# - Install fastmcp, requests, and snipeit-python-api
# - Set up the project for development
```

**Note:** The `uv sync` command will install all dependencies including:
- FastMCP framework
- Snipe-IT Python API client (from GitHub)
- PaddleOCR and dependencies for OCR label extraction
- Pydantic for data validation

### 3. Configure environment variables

Create a `.env` file or export these environment variables:

```bash
export SNIPEIT_URL="https://your-snipeit-instance.com"
export SNIPEIT_TOKEN="your-api-token-here"
```

Or create a `.env` file:

```env
SNIPEIT_URL=https://your-snipeit-instance.com
SNIPEIT_TOKEN=your-api-token-here
```

To get a Snipe-IT API token:
1. Log in to your Snipe-IT instance
2. Go to your user profile (click your name in the top right)
3. Navigate to "API Tokens" or "Personal Access Tokens"
4. Generate a new token with appropriate permissions

## Usage

### Running the Server

#### Method 1: Direct Python execution

```bash
# Make sure environment variables are set
export SNIPEIT_URL="https://your-snipeit-instance.com"
export SNIPEIT_TOKEN="your-api-token-here"

# Run the server
python server.py
```

#### Method 2: Using FastMCP CLI

```bash
# With environment variables
fastmcp run server.py:mcp --transport stdio

# Or with HTTP transport for remote access
fastmcp run server.py:mcp --transport http --port 8000
```

### Available Tools

The server provides the following tools for interacting with your Snipe-IT instance:

#### 1. `manage_assets`
Comprehensive asset management with CRUD operations.

**Actions:**
- `create`: Create a new asset
- `get`: Retrieve a single asset by ID, asset tag, or serial number
- `list`: List assets with optional pagination and filtering
- `update`: Update an existing asset
- `delete`: Delete an asset

**Example:**
```python
# Create an asset
{
    "action": "create",
    "asset_data": {
        "status_id": 1,
        "model_id": 5,
        "asset_tag": "LAP-001",
        "name": "Dell Laptop",
        "serial": "ABC123XYZ"
    }
}

# Get an asset by tag
{
    "action": "get",
    "asset_tag": "LAP-001"
}

# List assets
{
    "action": "list",
    "limit": 20,
    "search": "laptop"
}
```

#### 2. `asset_operations`
Perform state operations on assets.

**Actions:**
- `checkout`: Check out an asset to a user, location, or another asset
- `checkin`: Check in an asset back to inventory
- `audit`: Mark an asset as audited
- `restore`: Restore a soft-deleted asset

**Example:**
```python
# Checkout asset to user
{
    "action": "checkout",
    "asset_id": 123,
    "checkout_data": {
        "checkout_to_type": "user",
        "assigned_to_id": 45,
        "expected_checkin": "2025-12-31",
        "note": "Issued for remote work"
    }
}

# Checkin asset
{
    "action": "checkin",
    "asset_id": 123,
    "checkin_data": {
        "note": "Returned in good condition"
    }
}
```

#### 3. `asset_files`
Manage file attachments for assets.

**Actions:**
- `upload`: Upload one or more files to an asset
- `list`: List all files attached to an asset
- `download`: Download a specific file from an asset
- `delete`: Delete a specific file from an asset

**Example:**
```python
# Upload files
{
    "action": "upload",
    "asset_id": 123,
    "file_paths": ["/path/to/receipt.pdf", "/path/to/warranty.pdf"],
    "notes": "Purchase documentation"
}

# List files
{
    "action": "list",
    "asset_id": 123
}
```

#### 4. `asset_labels`
Generate printable PDF labels for assets.

**Example:**
```python
# Generate labels by asset IDs
{
    "asset_ids": [123, 124, 125],
    "save_path": "/tmp/asset_labels.pdf"
}

# Generate labels by asset tags
{
    "asset_tags": ["LAP-001", "LAP-002"],
    "save_path": "/tmp/labels.pdf"
}
```

#### 5. `asset_maintenance`
Create maintenance records for assets.

**Example:**
```python
{
    "action": "create",
    "asset_id": 123,
    "maintenance_data": {
        "asset_improvement": "repair",
        "supplier_id": 10,
        "title": "Screen Replacement",
        "cost": 250.00,
        "start_date": "2025-10-10",
        "completion_date": "2025-10-11",
        "notes": "Replaced cracked screen"
    }
}
```

#### 6. `asset_licenses`
Get all licenses checked out to an asset.

**Example:**
```python
{
    "asset_id": 123
}
```

#### 7. `manage_consumables`
Comprehensive consumable management with CRUD operations.

**Actions:**
- `create`: Create a new consumable
- `get`: Retrieve a single consumable by ID
- `list`: List consumables with optional pagination and filtering
- `update`: Update an existing consumable
- `delete`: Delete a consumable

**Example:**
```python
# Create a consumable
{
    "action": "create",
    "consumable_data": {
        "name": "USB-C Cable",
        "qty": 50,
        "category_id": 3,
        "min_amt": 10
    }
}

# List consumables
{
    "action": "list",
    "limit": 20,
    "search": "cable"
}
```

#### 8. `extract_label_data`
Extract asset data from NTUST (or other) label photos using OCR.

**Features:**
- Traditional Chinese OCR support using PaddleOCR
- Automatic ROC date conversion (民國年) to Gregorian dates
- Configurable field mappings for different label formats
- Returns structured data with confidence scores

**Parameters:**
- `image_path`: Path to the label photo
- `language`: OCR language (default: `chinese_cht` for Traditional Chinese)
- `field_mapping`: Optional custom field names (defaults to NTUST format)

**Default NTUST Field Mapping:**
- 財產編號 → asset_tag
- 取得日期 → purchase_date (auto-converts ROC dates)
- 序號 → serial
- 年限 → warranty_months (converts years to months)
- 財產名稱 → name
- 保管單位 → custodian_unit
- 保管人員 → custodian
- 規格 → specs
- 經費來源 → funding_source

**Example:**
```python
# Extract data from NTUST label
{
    "image_path": "/path/to/label_photo.jpg",
    "language": "chinese_cht"
}

# Returns:
{
    "success": true,
    "extracted_data": {
        "asset_tag": "3140101-03",
        "serial": "0231X2",
        "name": "主機含螢幕23吋+",
        "purchase_date": "2018-07-06",  # Converted from ROC 107.07.06
        "warranty_months": 48,  # Converted from 4 years
        "specs": "ASUSMD590",
        "custodian_unit": "電子系",
        "custodian": "鄭瑞光",
        "funding_source": "校務基金",
        "raw_ocr_text": "...",
        "confidence": 0.95
    }
}
```

#### 9. `import_asset_from_label`
One-step workflow: extract label data and create asset in Snipe-IT.

**Features:**
- Combines OCR extraction with asset creation
- Preview mode to review data before creating
- Automatically builds notes field with specs, custodian, and funding info

**Parameters:**
- `image_path`: Path to the label photo
- `status_id`: Required Snipe-IT status ID for the asset
- `model_id`: Required Snipe-IT model ID for the asset
- `location_id`: Optional location ID
- `preview_only`: If `true`, extract and return data without creating asset
- `language`: OCR language (default: `chinese_cht`)
- `field_mapping`: Optional custom field names

**Example:**
```python
# Preview extraction first
{
    "image_path": "/path/to/label.jpg",
    "status_id": 2,
    "model_id": 10,
    "preview_only": true
}

# Create asset after reviewing preview
{
    "image_path": "/path/to/label.jpg",
    "status_id": 2,
    "model_id": 10,
    "location_id": 5,
    "preview_only": false
}
```

#### 10. `batch_import_labels`
Process multiple label photos at once.

**Parameters:**
- `image_paths`: Array of image file paths
- `status_id`: Required status ID for all assets
- `model_id`: Required model ID for all assets
- `location_id`: Optional location ID for all assets
- `stop_on_error`: If `true`, stop processing on first error (default: `false`)

**Example:**
```python
{
    "image_paths": [
        "/path/to/label1.jpg",
        "/path/to/label2.jpg",
        "/path/to/label3.jpg"
    ],
    "status_id": 2,
    "model_id": 10,
    "location_id": 5,
    "stop_on_error": false
}

# Returns:
{
    "success": true,
    "success_count": 2,
    "failure_count": 1,
    "results": [
        {"image": "label1.jpg", "success": true, "asset_id": 123},
        {"image": "label2.jpg", "success": true, "asset_id": 124},
        {"image": "label3.jpg", "success": false, "error": "OCR failed"}
    ]
}
```

#### 11. `get_asset_qr_code`
Generate individual QR code or barcode images for assets.

**Features:**
- Fetch 2D QR codes or 1D barcodes as PNG images
- Save to local filesystem
- Look up by asset ID or asset tag

**Parameters:**
- `asset_id`: Asset ID (required if `asset_tag` not provided)
- `asset_tag`: Asset tag (alternative to `asset_id`)
- `save_path`: Where to save the PNG file (default: `/tmp/qr_code.png`)
- `code_type`: `"qr"` for 2D QR code or `"barcode"` for 1D barcode (default: `"qr"`)

**Example:**
```python
# Generate QR code by asset ID
{
    "asset_id": 123,
    "save_path": "/tmp/asset_123_qr.png",
    "code_type": "qr"
}

# Generate barcode by asset tag
{
    "asset_tag": "LAP-001",
    "save_path": "/tmp/lap001_barcode.png",
    "code_type": "barcode"
}
```

## Integration with MCP Clients

### Claude Desktop

Add this configuration to your Claude Desktop config file:

**Location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "snipeit": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/snipeit-mcp",
        "run",
        "python",
        "server.py"
      ],
      "env": {
        "SNIPEIT_URL": "https://your-snipeit-instance.com",
        "SNIPEIT_TOKEN": "your-api-token-here"
      }
    }
  }
}
```

### Cursor

Add this to your Cursor MCP settings:

```json
{
  "mcpServers": {
    "snipeit": {
      "command": "python",
      "args": ["/path/to/snipeit-mcp/server.py"],
      "env": {
        "SNIPEIT_URL": "https://your-snipeit-instance.com",
        "SNIPEIT_TOKEN": "your-api-token-here"
      }
    }
  }
}
```

## Architecture

The server is built using:

- **FastMCP**: A Python framework for building MCP servers
- **snipeit-python-api**: Python client library for Snipe-IT API
- **Pydantic**: Data validation and settings management

### Tool Design

The server consolidates operations into a minimal number of tools:

- Single tool for Asset CRUD operations (`manage_assets`)
- Single tool for Asset state operations (`asset_operations`)
- Specialized tools for specific features (files, labels, maintenance, licenses)
- Single tool for Consumable CRUD operations (`manage_consumables`)
- OCR-based label extraction tools for automated data entry (`extract_label_data`, `import_asset_from_label`, `batch_import_labels`)
- QR code generation tool for individual code images (`get_asset_qr_code`)

This design minimizes the cognitive load on AI assistants while providing comprehensive functionality.

### ROC Date Conversion

The server includes automatic conversion of ROC (Republic of China/Taiwan calendar) dates to Gregorian dates:

- ROC year calculation: `ROC year + 1911 = Gregorian year`
- Example: `107.07.06` → `2018-07-06`
- Supports multiple separators: `.`, `-`, `/`
- Used in label extraction for NTUST and other Taiwan-based institutions

## Error Handling

All tools return structured responses with success status:

```json
{
  "success": true,
  "action": "create",
  "asset": {
    "id": 123,
    "asset_tag": "LAP-001",
    "name": "Dell Laptop"
  }
}
```

Error responses include descriptive messages:

```json
{
  "success": false,
  "error": "Asset not found: Asset with tag LAP-999 not found."
}
```

## Troubleshooting

### Authentication Errors

**Problem:** "Authentication failed" error

**Solution:** 
- Verify your Snipe-IT URL is correct and accessible
- Check that your API token is valid and not expired
- Ensure the token has appropriate permissions

### Connection Errors

**Problem:** Cannot connect to Snipe-IT instance

**Solution:**
- Verify the URL is correct (include `https://` or `http://`)
- Check network connectivity
- Ensure Snipe-IT instance is running and accessible

### Tool Execution Errors

**Problem:** Tool returns validation errors

**Solution:**
- Check that required fields are provided (e.g., `status_id` and `model_id` for asset creation)
- Verify foreign key IDs exist (e.g., category_id, model_id)
- Review the tool documentation for required parameters

### Environment Variable Issues

**Problem:** "Snipe-IT credentials not configured" error

**Solution:**
- Ensure `SNIPEIT_URL` and `SNIPEIT_TOKEN` are set in your environment
- If using a `.env` file, make sure it's in the correct location
- Check that the variables are exported before running the server

### OCR Issues

**Problem:** "PaddleOCR not available" error

**Solution:**
- Install OpenCV system libraries: `brew install opencv` (macOS)
- Run `uv sync` to install PaddleOCR dependencies
- On first OCR run, PaddleOCR will download language models (~10-20MB)

**Problem:** OCR extraction returns low confidence or missing fields

**Solution:**
- Ensure label photo is clear and well-lit
- Check that the image is not rotated (PaddleOCR handles rotation automatically)
- Verify field names match your label format (use custom `field_mapping` if needed)
- Try higher resolution photos for better OCR accuracy

**Problem:** ROC date conversion fails

**Solution:**
- Verify date format matches ROC convention: `YYY.MM.DD` (e.g., `107.07.06`)
- Supported separators: `.`, `-`, `/`
- Date must have 2-3 digit year, 2-digit month, 2-digit day

## Development

### Project Structure

```
snipeit-mcp/
├── server.py           # Main MCP server implementation
├── pyproject.toml      # Project configuration and dependencies
├── README.md           # This file
├── test_helpers.py     # Unit tests for OCR helper functions
├── .gitignore         # Git ignore rules
└── .venv/             # Virtual environment (created by uv)
```

### Testing

Run the helper function tests:

```bash
# Run OCR helper tests
uv run python test_helpers.py
```

This validates:
- ROC date conversion (民國年 → Gregorian)
- Field extraction from Chinese labels
- Label parsing logic

### Running in Development Mode

```bash
# Activate virtual environment
source .venv/bin/activate

# Run with debug logging
export LOG_LEVEL=DEBUG
python server.py
```

## License

This project is provided as-is for use with Snipe-IT inventory management systems.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues related to:
- **This MCP Server**: Open an issue in this repository
- **Snipe-IT**: Visit [Snipe-IT support](https://snipeitapp.com/support)
- **FastMCP**: Visit [FastMCP documentation](https://gofastmcp.com)

## Acknowledgments

- Built with [FastMCP](https://gofastmcp.com)
- Uses [snipeit-python-api](https://github.com/lfctech/snipeit-python-api) for Snipe-IT integration
- OCR powered by [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) for Traditional Chinese text recognition
- Designed for [Snipe-IT](https://snipeitapp.com/) asset management system

## Changelog

### 2026-07-06
- Added OCR-based label extraction for NTUST asset labels
- Implemented Traditional Chinese OCR support using PaddleOCR
- Added automatic ROC (Taiwan calendar) to Gregorian date conversion
- Added `extract_label_data` tool for label OCR extraction
- Added `import_asset_from_label` workflow tool for one-step import
- Added `batch_import_labels` tool for bulk label processing
- Added `get_asset_qr_code` tool for individual QR/barcode image generation
- Fixed hardcoded dependency path in pyproject.toml
- Added comprehensive OCR troubleshooting documentation
