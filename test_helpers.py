#!/usr/bin/env python3
"""Test helper functions for label extraction."""

import warnings
warnings.filterwarnings('ignore')

from server import convert_roc_to_gregorian, extract_field_value, LabelFieldMapping

def test_roc_date_conversion():
    """Test ROC to Gregorian date conversion."""
    print('Testing ROC date conversion:')
    test_dates = ['107.07.06', '107-07-06', '107/07/06']
    for date in test_dates:
        result = convert_roc_to_gregorian(date)
        print(f'  {date} -> {result}')
        assert result == '2018-07-06', f"Expected 2018-07-06, got {result}"

def test_field_extraction():
    """Test field extraction from OCR text."""
    print('\nTesting field extraction:')
    sample_text = '''財產編號: 3140101-03
取得日期: 107.07.06
序號: 0231X2
年限: 4
財產名稱: 主機含螢幕23吋+
保管單位: 電子系
保管人員: 鄭瑞光
規格: ASUSMD590
經費來源: 校務基金'''

    mapping = LabelFieldMapping()
    
    asset_number = extract_field_value(sample_text, mapping.asset_number)
    acquisition_date = extract_field_value(sample_text, mapping.acquisition_date)
    serial = extract_field_value(sample_text, mapping.serial_number)
    asset_name = extract_field_value(sample_text, mapping.asset_name)
    custodian_unit = extract_field_value(sample_text, mapping.custodian_unit)
    
    print(f'  Asset Number: {asset_number}')
    print(f'  Acquisition Date: {acquisition_date}')
    print(f'  Serial: {serial}')
    print(f'  Asset Name: {asset_name}')
    print(f'  Custodian Unit: {custodian_unit}')
    
    assert asset_number == '3140101-03', f"Expected 3140101-03, got {asset_number}"
    assert acquisition_date == '107.07.06', f"Expected 107.07.06, got {acquisition_date}"
    assert serial == '0231X2', f"Expected 0231X2, got {serial}"

if __name__ == '__main__':
    test_roc_date_conversion()
    test_field_extraction()
    print('\n✓ All tests passed!')
