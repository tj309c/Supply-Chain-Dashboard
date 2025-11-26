"""
Business Rules Configuration
Centralized definitions for fields, calculations, and business logic.
This file allows rules to be changed in one place without modifying tool code.
"""

from datetime import datetime
import pandas as pd

# ===== CURRENCY CONVERSION =====

CURRENCY_RULES = {
    "base_currency": "USD",
    "supported_currencies": ["USD", "EUR"],
    "conversion_rates": {
        "USD_to_EUR": 0.9,
        "EUR_to_USD": 1.0 / 0.9
    }
}


# ===== INVENTORY CLASSIFICATION RULES =====

INVENTORY_RULES = {
    "movement_classification": {
        # DIO thresholds for classifying inventory movement
        "fast_moving_days": 30,
        "normal_moving_days": 60,
        "slow_moving_days": 90,
        "very_slow_moving_days": 180,
        # Anything above very_slow_moving_days is "Obsolete Risk"
        # DIO = 0 (no movement) is "Dead Stock"
    },

    "scrap_criteria": {
        # Default threshold for scrap candidates (in days)
        "default_dio_threshold": 730,  # 2 years
        "min_dio_threshold": 90,        # Minimum allowed in UI
        "max_dio_threshold": 1825,      # Maximum allowed in UI (5 years)
        "include_dead_stock": True      # Include items with no movement
    },

    "scrap_recommendation_system": {
        # 3-Level data-driven scrap recommendation system
        # Business Logic: OLDER SKUs with excess inventory = MORE aggressive candidates
        # (More historical data = higher confidence in overstocking diagnosis)

        "min_sku_age_days": 365,  # Minimum SKU age for any scrap recommendations (1 year)

        "conservative": {
            "description": "Conservative approach for older SKUs with very low demand",
            "min_sku_age_days": 1095,  # >3 years old
            "max_quarters_with_demand": 1,  # Low demand frequency (<=1 quarter)
            "safety_stock_days": 365,  # Keep 12 months supply
            "criteria": "Older SKUs (>3 years) + very low demand frequency"
        },

        "medium": {
            "description": "Moderate approach for established SKUs",
            "min_sku_age_days": 730,  # >2 years old
            "safety_stock_days": 180,  # Keep 6 months supply (base)
            "safety_stock_days_aggressive": 90,  # Keep 3 months (Class C/discontinued/superseded)
            "criteria": "Moderate age SKUs (>2 years) with adjustments for ABC class, PLM status, alternate codes",
            "aggressive_triggers": [
                "ABC Class C (low value items)",
                "Discontinued or expired PLM status",
                "Superseded SKUs (old alternate codes)"
            ]
        },

        "aggressive": {
            "description": "Aggressive approach leveraging historical data confidence",
            "min_sku_age_days": 365,  # >1 year old (base requirement)
            "safety_stock_days_base": 90,  # Keep 3 months supply (base)
            "safety_stock_days_very_aggressive": 60,  # Keep 2 months (>3 years old)
            "safety_stock_days_extra_aggressive": 30,  # Keep 1 month (old + Class C/discontinued/superseded)
            "very_aggressive_age_days": 1095,  # >3 years triggers very aggressive mode
            "criteria": "Established SKUs (>1 year) with graduated aggressiveness based on age and risk factors",
            "logic": "Older SKUs have more data points → higher confidence → more aggressive scrapping"
        },

        "dead_stock_handling": {
            "description": "Items with no demand in historical period",
            "criteria": "daily_demand = 0 AND sku_age_days > 365",
            "action": "Scrap 100% across all levels (conservative, medium, aggressive)"
        },

        "exclusions": {
            "young_skus": {
                "threshold_days": 365,
                "reason": "SKUs < 1 year old excluded - insufficient historical data for accurate recommendations"
            }
        },

        "data_sources": {
            "sku_age": "Activation Date (Code) from Master Data",
            "demand_frequency": "Q1-Q4 demand from Deliveries (last 4 quarters)",
            "demand_history": "Rolling 1-year usage from Deliveries",
            "abc_classification": "Calculated from inventory value (cumulative % of total value)",
            "plm_status": "PLM Current Status from Master Data",
            "alternate_codes": "ALTERNATE_CODES.csv (superseded SKU identification)"
        },

        "output_format": {
            "columns": [
                "Conservative Scrap Qty",
                "Conservative Scrap Value (USD)",
                "Medium Scrap Qty",
                "Medium Scrap Value (USD)",
                "Aggressive Scrap Qty",
                "Aggressive Scrap Value (USD)"
            ],
            "description": "6 additional columns added to warehouse scrap list export"
        }
    },

    "abc_analysis": {
        # Percentage thresholds for ABC classification
        "a_class_threshold": 80,  # Top 80% of value
        "b_class_threshold": 95,  # Next 15% of value (80-95%)
        # C class is remaining 5%

        # Alternative: Count-based thresholds
        "use_count_based": False,  # If True, use SKU count instead of value
        "a_class_count_pct": 20,   # Top 20% of SKUs by value
        "b_class_count_pct": 30    # Next 30% of SKUs
    },

    "stock_out_risk": {
        # DIO thresholds for stock-out risk alerts
        "critical_dio": 7,   # Critical risk: less than 7 days
        "warning_dio": 14,   # Warning: less than 14 days
        "safe_dio": 30       # Safe: more than 30 days
    },

    "demand_calculation": {
        # Historical period for demand calculation
        "lookback_months": 12,
        "lookback_days": 365,

        # SKU Age-Based Demand Calculation
        # New SKUs should use actual days in market, not full 365 days
        "sku_market_intro_buffer_days": 60,  # SKU creation date + 2 months = market intro date
        "use_sku_age_adjustment": True,       # Enable SKU age-based divisor
        "min_days_for_demand_calc": 30        # Minimum days required before calculating demand
    },

    "variable_buckets": {
        # Allow users to configure custom DIO bucket boundaries
        "enabled": True,
        "default_boundaries": [30, 60, 90, 180, 365, 730],  # Default DIO bucket edges
        "min_boundary": 1,
        "max_boundary": 1825,
        "bucket_labels_auto": True  # Auto-generate labels like "0-30 days", "30-60 days"
    },

    "snapshot_frequency": {
        # For future monthly snapshots feature
        "snapshot_interval": "monthly",  # monthly, weekly, daily
        "retention_months": 24           # Keep 24 months of history
    }
}


# ===== SERVICE LEVEL RULES =====

SERVICE_LEVEL_RULES = {
    "on_time_delivery": {
        # Lead time for on-time calculation (days after order)
        "standard_lead_time_days": 7,
        "target_on_time_percentage": 95.0
    },

    "performance_thresholds": {
        "excellent": 95.0,  # >= 95% on-time
        "good": 90.0,       # >= 90% on-time
        "fair": 85.0,       # >= 85% on-time
        # Below fair is "poor"
    }
}


# ===== BACKORDER RULES =====

BACKORDER_RULES = {
    "aging_calculation": {
        # IMPORTANT: Backorder age is calculated from ORDER CREATION DATE
        # Age = Today - Order Creation Date
        # This is the authoritative starting point for all backorder aging calculations
        "start_date_field": "order_date",
        "use_order_creation_date": True
    },

    "aging_buckets": {
        # Age ranges for backorder classification (in days)
        "buckets": [
            {"name": "0-7 days", "min": 0, "max": 7},
            {"name": "8-14 days", "min": 8, "max": 14},
            {"name": "15-30 days", "min": 15, "max": 30},
            {"name": "31-60 days", "min": 31, "max": 60},
            {"name": "60+ days", "min": 61, "max": 99999}
        ]
    },

    "priority_scoring": {
        # Factors for backorder priority calculation
        "age_weight": 0.4,
        "quantity_weight": 0.3,
        "customer_tier_weight": 0.3
    },

    "alerts": {
        "critical_age_days": 30,  # Alert if backorder > 30 days
        "high_quantity_threshold": 1000  # Alert if quantity > 1000 units
    }
}


# ===== STORAGE LOCATION RULES =====

STORAGE_LOCATION_RULES = {
    "locations": {
        "Z401": {
            "description": "POP AIT",
            "status": "Vendor Managed",
            "category": "vendor_managed",
            "availability": "external"
        },
        "Z303": {
            "description": "ATL PhantomTrans",
            "status": "Missing",
            "category": "missing",
            "availability": "unavailable"
        },
        "Z109": {
            "description": "POP ATL Whs Sloc",
            "status": "On Hand",
            "category": "on_hand",
            "availability": "available"
        },
        "Z799": {
            "description": "Com Pool transf",
            "status": "Unknown",
            "category": "unknown",
            "availability": "unknown"
        },
        "Z101": {
            "description": "DWM Main Storage",
            "status": "On Hand",
            "category": "on_hand",
            "availability": "available"
        },
        "Z106": {
            "description": "AFA ATL DWM WH",
            "status": "On Hand",
            "category": "on_hand",
            "availability": "available"
        },
        "Z307": {
            "description": "POP Transit : IT",
            "status": "Incoming from Italy",
            "category": "in_transit",
            "availability": "pending"
        },
        "Z503": {
            "description": "Write OFF S.ATL",
            "status": "Scrapped",
            "category": "scrapped",
            "availability": "unavailable"
        },
        "Z308": {
            "description": "POP Transit China",
            "status": "Incoming from China",
            "category": "in_transit",
            "availability": "pending"
        },
        "Z501": {
            "description": "Scrap Returns",
            "status": "Scrapped",
            "category": "scrapped",
            "availability": "unavailable"
        },
        "Z402": {
            "description": "POP Ryan Scott",
            "status": "Vendor Managed",
            "category": "vendor_managed",
            "availability": "external"
        },
        "Z116": {
            "description": "STELLA Stock",
            "status": "On Hand",
            "category": "on_hand",
            "availability": "available"
        }
    },

    "status_types": [
        "Vendor Managed",
        "On Hand",
        "Missing",
        "Unknown",
        "Scrapped",
        "Incoming from Italy",
        "Incoming from China"
    ],

    "categories": {
        "on_hand": ["Z109", "Z101", "Z106", "Z116"],
        "vendor_managed": ["Z401", "Z402"],
        "in_transit": ["Z307", "Z308"],
        "scrapped": ["Z503", "Z501"],
        "missing": ["Z303"],
        "unknown": ["Z799"]
    },

    "availability_mapping": {
        "available": "Can be used for order fulfillment",
        "pending": "Expected to arrive, not yet available",
        "external": "Managed by vendor, not in direct control",
        "unavailable": "Not available for use",
        "unknown": "Status unclear, needs investigation"
    }
}


# ===== ALTERNATE CODES RULES =====

ALTERNATE_CODES_RULES = {
    "normalization": {
        "auto_normalize": True,  # Automatically normalize old codes to current codes
        "normalize_inventory": True,  # Aggregate inventory across alternate codes
        "normalize_demand": True,  # Aggregate historical demand across alternate codes
        "normalize_backorders": True,  # Show backorders with current code reference
        "default_view": "aggregated"  # Default view: "aggregated" or "split"
    },

    "display": {
        "show_alternate_codes": True,  # Show alternate codes in tooltips/columns
        "show_code_transition_dates": False,  # Show when code changed (if data available)
        "highlight_old_codes": True,  # Highlight when displaying old code data
        "max_alternates_display": 3  # Maximum alternate codes to show in tooltip
    },

    "alerts": {
        "alert_on_old_code_backorders": True,  # Alert when backorders exist on old codes
        "alert_on_split_inventory": True,  # Alert when inventory split across codes
        "alert_on_old_code_orders": True,  # Alert when new orders use old codes
        "critical_backorder_threshold": 0  # Alert on ANY old code backorder
    },

    "business_logic": {
        # When backorder exists on old code and inventory exists on current code
        "recommend_code_update": True,  # Recommend updating order to current code
        "prioritize_old_inventory_first": True,  # Use old SKU inventory first before new
        "track_inventory_by_code": True,  # Track which code has which inventory
        "consolidate_reporting": True  # Consolidate all reports under current code
    },

    "data_quality": {
        "flag_missing_current_codes": True,  # Flag if current code not in master data
        "flag_circular_references": True,  # Flag if A→B→A code mappings exist
        "validate_code_hierarchy": True  # Ensure current code is truly current
    }
}


# ===== LEAD TIME RULES =====

LEAD_TIME_RULES = {
    "calculation_method": {
        # Lead time = Posting Date (receipt) - Order Creation Date (PO)
        "formula": "receipt_date - po_creation_date",
        "aggregation": "median",  # Use median instead of average to handle outliers
        "lookback_period_days": 730,  # Use last 2 years of historical data
        "safety_stock_buffer_days": 5  # Add 5 days safety stock to calculated lead times
    },

    "confidence_levels": {
        # Confidence based on number of historical POs
        "high_confidence_min_pos": 5,   # >=5 POs = High confidence
        "medium_confidence_min_pos": 2, # 2-4 POs = Medium confidence
        # <2 POs = Low confidence, use default
    },

    "defaults": {
        # Default lead time when no historical data available
        "default_lead_time_days": 90,  # Conservative 90-day estimate
        "reason": "Conservative industry standard for items without PO history"
    },

    "data_sources": {
        "vendor_pos": "Domestic Vendor POs.csv",
        "inbound_receipts": "Inbound_DB.csv"
    }
}


# ===== DATA FIELD DEFINITIONS =====

DATA_FIELD_DEFINITIONS = {
    "INVENTORY.csv": {
        "file_description": "Current inventory snapshot with on-hand quantities and pricing",
        "fields": {
            "Material Number": {
                "description": "Unique SKU/Material identifier (SAP Material Code)",
                "data_type": "string",
                "required": True,
                "used_for": ["inventory_tracking", "master_data_join"]
            },
            "POP Actual Stock Qty": {
                "description": "Current on-hand quantity in stock",
                "data_type": "numeric",
                "required": True,
                "used_for": ["inventory_value", "dio_calculation", "stock_out_risk"]
            },
            "POP Actual Stock in Transit Qty": {
                "description": "Quantity in transit (not yet received)",
                "data_type": "numeric",
                "required": False,
                "used_for": ["available_inventory", "planning"]
            },
            "POP Last Purchase: Price in Purch. Currency": {
                "description": "Last purchase price per unit (used for inventory valuation)",
                "data_type": "numeric",
                "required": True,
                "used_for": ["inventory_value", "scrap_value_calculation"]
            },
            "POP Last Purchase: Currency": {
                "description": "Currency of last purchase price (USD, EUR, etc.)",
                "data_type": "string",
                "required": True,
                "used_for": ["currency_conversion", "inventory_value"]
            }
        }
    },

    "DELIVERIES.csv": {
        "file_description": "Historical shipment/delivery records",
        "fields": {
            "Deliveries Detail - Order Document Number": {
                "description": "Order number (links to ORDERS.csv)",
                "data_type": "string",
                "required": True,
                "used_for": ["order_join", "service_level"]
            },
            "Item - SAP Model Code": {
                "description": "SKU/Material code for delivered item",
                "data_type": "string",
                "required": True,
                "used_for": ["demand_calculation", "dio_calculation"]
            },
            "Delivery Creation Date: Date": {
                "description": "Date when shipment was created/shipped (format: MM/DD/YY)",
                "data_type": "date",
                "format": "%m/%d/%y",
                "required": True,
                "used_for": ["service_level", "demand_calculation", "historical_trends"]
            },
            "Deliveries - TOTAL Goods Issue Qty": {
                "description": "Quantity of units shipped/delivered",
                "data_type": "numeric",
                "required": True,
                "used_for": ["demand_calculation", "service_level"]
            },
            "Item - Model Desc": {
                "description": "Product/item description",
                "data_type": "string",
                "required": False,
                "used_for": ["display", "reporting"]
            }
        }
    },

    "ORDERS.csv": {
        "file_description": "Customer orders and backorder tracking",
        "fields": {
            "Orders Detail - Order Document Number": {
                "description": "Unique order number",
                "data_type": "string",
                "required": True,
                "used_for": ["order_tracking", "delivery_join"]
            },
            "Item - SAP Model Code": {
                "description": "SKU/Material code for ordered item",
                "data_type": "string",
                "required": True,
                "used_for": ["order_tracking", "backorder_analysis"]
            },
            "Order Creation Date: Date": {
                "description": "Date when order was created (format: MM/DD/YY)",
                "data_type": "date",
                "format": "%m/%d/%y",
                "required": True,
                "used_for": ["service_level", "backorder_aging", "demand_analysis"]
            },
            "Original Customer Name": {
                "description": "Customer who placed the order",
                "data_type": "string",
                "required": True,
                "used_for": ["customer_analysis", "service_level_reporting"]
            },
            "Item - Model Desc": {
                "description": "Product/item description",
                "data_type": "string",
                "required": False,
                "used_for": ["display", "reporting"]
            },
            "Sales Organization Code": {
                "description": "Sales org responsible for order",
                "data_type": "string",
                "required": False,
                "used_for": ["organizational_reporting", "filtering"]
            },
            "Orders - TOTAL Orders Qty": {
                "description": "Total quantity ordered",
                "data_type": "numeric",
                "required": True,
                "used_for": ["order_tracking", "demand_analysis"]
            },
            "Orders - TOTAL To Be Delivered Qty": {
                "description": "Quantity still to be delivered (backorder quantity)",
                "data_type": "numeric",
                "required": True,
                "used_for": ["backorder_tracking", "fulfillment_analysis"]
            },
            "Orders - TOTAL Cancelled Qty": {
                "description": "Quantity cancelled from order",
                "data_type": "numeric",
                "required": False,
                "used_for": ["cancellation_analysis", "order_accuracy"]
            },
            "Reject Reason Desc": {
                "description": "Reason for rejection/cancellation",
                "data_type": "string",
                "required": False,
                "used_for": ["root_cause_analysis"]
            },
            "Order Type (SAP) Code": {
                "description": "Type of order (standard, rush, etc.)",
                "data_type": "string",
                "required": False,
                "used_for": ["order_classification", "filtering"]
            },
            "Order Reason Code": {
                "description": "Reason code for order",
                "data_type": "string",
                "required": False,
                "used_for": ["order_classification"]
            }
        }
    },

    "Master Data.csv": {
        "file_description": "Product catalog with SKU metadata",
        "fields": {
            "Material Number": {
                "description": "Unique SKU/Material identifier",
                "data_type": "string",
                "required": True,
                "used_for": ["master_lookup", "joins"]
            },
            "PLM: Level Classification 4": {
                "description": "Product category/classification",
                "data_type": "string",
                "required": True,
                "used_for": ["category_analysis", "filtering", "abc_analysis"]
            },
            "Activation Date (Code)": {
                "description": "SKU creation/activation date (format: M/D/YY). Used to determine market introduction date for demand calculations.",
                "data_type": "date",
                "required": False,
                "used_for": ["demand_calculation", "sku_age_analysis", "new_product_identification"]
            }
        }
    },

    "Inbound_DB.csv": {
        "file_description": "Consolidated inbound receipts and PO tracking (domestic and international)",
        "fields": {
            "Purchase Order Number": {
                "description": "PO number (links to Vendor POs)",
                "data_type": "string",
                "required": True,
                "used_for": ["po_tracking", "lead_time_calculation"]
            },
            "Date": {
                "description": "Receipt/posting date (YYYYMMDD format)",
                "data_type": "date",
                "required": True,
                "used_for": ["lead_time_calculation", "receipt_tracking"]
            },
            "Material Number": {
                "description": "SKU/Material code received",
                "data_type": "string",
                "required": True,
                "used_for": ["inventory_updates", "lead_time_calculation"]
            },
            "*Purchase Orders IC Flag": {
                "description": "International/Domestic flag (YES=international, NO=domestic)",
                "data_type": "string",
                "required": True,
                "used_for": ["vendor_segmentation", "kpi_filtering"]
            },
            "POP Good Receipts Quantity": {
                "description": "Quantity received on this receipt",
                "data_type": "numeric",
                "required": True,
                "used_for": ["receipt_tracking", "fill_rate_calculation"]
            },
            "POP Good Receipts on Time Quantity": {
                "description": "Pre-calculated on-time receipt quantity",
                "data_type": "numeric",
                "required": False,
                "used_for": ["on_time_delivery_kpi"]
            },
            "POP Purchase Order Open Overdue Quantity": {
                "description": "Pre-calculated open overdue quantity",
                "data_type": "numeric",
                "required": False,
                "used_for": ["overdue_kpi", "fill_rate_calculation"]
            },
            "PLM: Level Classification 4": {
                "description": "Product category classification (e.g., RETAIL PERMANENT, WHLS SEASONAL)",
                "data_type": "string",
                "required": False,
                "used_for": ["category_filtering", "segmentation"]
            }
        }
    },

    "Domestic Vendor POs.csv": {
        "file_description": "Purchase orders from vendors",
        "fields": {
            "SAP Purchase Orders - Purchasing Document Number": {
                "description": "Unique PO number",
                "data_type": "string",
                "required": True,
                "used_for": ["po_tracking", "vendor_performance"]
            },
            "Order Creation Date - Date": {
                "description": "Date when PO was created",
                "data_type": "date",
                "required": True,
                "used_for": ["lead_time_calculation", "po_aging"]
            },
            "SAP Material Code": {
                "description": "SKU/Material code ordered",
                "data_type": "string",
                "required": True,
                "used_for": ["inventory_planning", "lead_time_by_sku"]
            }
        }
    }
}


# ===== CALCULATED FIELDS =====

CALCULATED_FIELDS = {
    "dio": {
        "name": "Days Inventory Outstanding",
        "formula": "on_hand_qty / daily_demand",
        "description": "Number of days current inventory will last based on historical demand",
        "interpretation": {
            "0": "No movement in historical period (dead stock)",
            "< 30": "Fast moving - less than 1 month of supply",
            "30-60": "Normal moving - 1-2 months of supply",
            "60-90": "Slow moving - 2-3 months of supply",
            "90-180": "Very slow moving - 3-6 months of supply",
            "> 180": "Obsolete risk - more than 6 months of supply"
        },
        "notes": "Daily demand calculated from last 12 months of deliveries / 365 days"
    },

    "daily_demand": {
        "name": "Daily Demand",
        "formula": "sum(deliveries_since_market_intro) / days_since_market_intro",
        "description": "Average daily demand based on historical shipments since SKU market introduction",
        "lookback_period": "From SKU creation date + 2 months, up to 12 months maximum",
        "calculation_logic": {
            "step_1": "Determine market intro date = Activation Date (Code) + 60 days",
            "step_2": "Calculate days_active = Today - market_intro_date",
            "step_3": "Use min(days_active, 365) as divisor for daily demand",
            "step_4": "SKUs with <30 days active excluded from demand calculations"
        },
        "notes": "Uses DELIVERIES.csv and Master Data.csv (Activation Date). New SKUs (<2 months old) are excluded from demand calculations. Uses actual days active, capped at 365."
    },

    "stock_value": {
        "name": "Stock Value",
        "formula": "on_hand_qty * last_purchase_price",
        "description": "Total value of on-hand inventory",
        "currency": "Based on 'POP Last Purchase: Currency' field",
        "notes": "Can be converted to USD or EUR for reporting"
    },

    "movement_class": {
        "name": "Movement Classification",
        "formula": "Based on DIO thresholds (see INVENTORY_RULES)",
        "description": "Classification of inventory movement speed",
        "categories": [
            "Fast Moving (DIO <= 30)",
            "Normal Moving (30 < DIO <= 60)",
            "Slow Moving (60 < DIO <= 90)",
            "Very Slow Moving (90 < DIO <= 180)",
            "Obsolete Risk (DIO > 180)",
            "Dead Stock (DIO = 0)"
        ]
    },

    "days_on_backorder": {
        "name": "Days on Backorder",
        "formula": "today - order_date",
        "description": "Number of days an order has been on backorder",
        "notes": "Calculated from order creation date to today"
    },

    "days_to_deliver": {
        "name": "Days to Deliver",
        "formula": "ship_date - order_date",
        "description": "Number of days from order creation to shipment",
        "notes": "Used for service level performance tracking"
    },

    "on_time": {
        "name": "On-Time Delivery Flag",
        "formula": "ship_date <= (order_date + 7 days)",
        "description": "Boolean flag indicating if delivery was on-time",
        "threshold": "7 days (configurable in SERVICE_LEVEL_RULES)",
        "notes": "Used to calculate on-time delivery percentage"
    }
}


# ===== HELPER FUNCTIONS =====

def convert_currency(value, from_currency, to_currency):
    """
    Convert a value from one currency to another using defined conversion rates.

    Args:
        value: Numeric value to convert
        from_currency: Source currency code (e.g., 'USD', 'EUR')
        to_currency: Target currency code (e.g., 'USD', 'EUR')

    Returns:
        Converted value, or original value if conversion not possible
    """
    if value is None or from_currency == to_currency:
        return value

    from_currency = str(from_currency).upper()
    to_currency = str(to_currency).upper()

    conversion_key = f"{from_currency}_to_{to_currency}"
    rates = CURRENCY_RULES.get("conversion_rates", {})

    if conversion_key in rates:
        return value * rates[conversion_key]

    # Try reverse conversion
    reverse_key = f"{to_currency}_to_{from_currency}"
    if reverse_key in rates:
        return value / rates[reverse_key]

    # No conversion available, return original value
    return value


def get_scrap_threshold(user_input=None):
    """
    Get the scrap threshold in days, with validation.

    Args:
        user_input: User-specified threshold (optional)

    Returns:
        Validated threshold in days
    """
    default = INVENTORY_RULES["scrap_criteria"]["default_dio_threshold"]

    if user_input is None:
        return default

    min_val = INVENTORY_RULES["scrap_criteria"]["min_dio_threshold"]
    max_val = INVENTORY_RULES["scrap_criteria"]["max_dio_threshold"]

    # Validate and clamp to allowed range
    return max(min_val, min(max_val, user_input))


def get_movement_classification(dio_value):
    """
    Classify inventory movement based on DIO value.

    Args:
        dio_value: Days Inventory Outstanding

    Returns:
        Movement classification string
    """
    rules = INVENTORY_RULES["movement_classification"]

    if dio_value == 0:
        return "Dead Stock"
    elif dio_value <= rules["fast_moving_days"]:
        return "Fast Moving"
    elif dio_value <= rules["normal_moving_days"]:
        return "Normal Moving"
    elif dio_value <= rules["slow_moving_days"]:
        return "Slow Moving"
    elif dio_value <= rules["very_slow_moving_days"]:
        return "Very Slow Moving"
    else:
        return "Obsolete Risk"


def get_stock_out_risk_level(dio_value):
    """
    Determine stock-out risk level based on DIO.

    Args:
        dio_value: Days Inventory Outstanding

    Returns:
        Risk level string: "Critical", "Warning", "Safe", or "Unknown"
    """
    rules = INVENTORY_RULES["stock_out_risk"]

    if dio_value == 0:
        return "Out of Stock"
    elif dio_value < rules["critical_dio"]:
        return "Critical"
    elif dio_value < rules["warning_dio"]:
        return "Warning"
    elif dio_value >= rules["safe_dio"]:
        return "Safe"
    else:
        return "Monitor"


def get_storage_location_info(location_code):
    """
    Get information about a storage location.

    Args:
        location_code: Storage location code (e.g., "Z101")

    Returns:
        Dictionary with location info or None if not found
    """
    locations = STORAGE_LOCATION_RULES.get("locations", {})
    return locations.get(location_code)


def get_storage_locations_by_category(category):
    """
    Get all storage location codes for a specific category.

    Args:
        category: Category name (e.g., "on_hand", "in_transit", "scrapped")

    Returns:
        List of storage location codes
    """
    categories = STORAGE_LOCATION_RULES.get("categories", {})
    return categories.get(category, [])


# ===== ALTERNATE CODES HELPER FUNCTIONS =====

# Global cache for alternate codes mapping
_ALTERNATE_CODES_CACHE = None


def load_alternate_codes_mapping(file_path="ALTERNATE_CODES.csv"):
    """
    Load and parse the alternate codes mapping file.

    Args:
        file_path: Path to ALTERNATE_CODES.csv

    Returns:
        Dictionary with bidirectional mappings:
        {
            'current_to_old': {current_code: [old_code1, old_code2, ...]},
            'old_to_current': {old_code: current_code},
            'all_codes_by_family': {current_code: [current, old1, old2, ...]}
        }
    """
    global _ALTERNATE_CODES_CACHE

    # Return cached version if available
    if _ALTERNATE_CODES_CACHE is not None:
        return _ALTERNATE_CODES_CACHE

    import pandas as pd
    import os

    # Initialize mappings
    current_to_old = {}
    old_to_current = {}
    all_codes_by_family = {}

    # Resolve file path relative to this file's directory (project root)
    if not os.path.isabs(file_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, file_path)

    if not os.path.exists(file_path):
        print(f"Warning: Alternate codes file not found at {file_path}")
        _ALTERNATE_CODES_CACHE = {
            'current_to_old': current_to_old,
            'old_to_current': old_to_current,
            'all_codes_by_family': all_codes_by_family
        }
        return _ALTERNATE_CODES_CACHE

    try:
        # Load CSV - try multiple encodings
        try:
            df = pd.read_csv(file_path, dtype=str, encoding='utf-8')
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(file_path, dtype=str, encoding='latin-1')
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, dtype=str, encoding='cp1252')

        # Expected columns
        col_current = 'SAP Material Current'
        col_last_old = 'SAP Material Last Old Code'
        col_original = 'SAP Material Original Code'

        # Rename columns to be compatible with itertuples (replace spaces with underscores)
        df.columns = [c.replace(' ', '_') for c in df.columns]
        col_current_safe = col_current.replace(' ', '_')
        col_last_old_safe = col_last_old.replace(' ', '_')
        col_original_safe = col_original.replace(' ', '_')

        # Use itertuples() instead of iterrows() for 100x faster performance
        for row in df.itertuples():
            current_code = str(getattr(row, col_current_safe)).strip() if pd.notna(getattr(row, col_current_safe, None)) else None
            last_old_code = str(getattr(row, col_last_old_safe)).strip() if pd.notna(getattr(row, col_last_old_safe, None)) else None
            original_code = str(getattr(row, col_original_safe)).strip() if pd.notna(getattr(row, col_original_safe, None)) else None

            # Skip if no current code
            if not current_code or current_code in ('nan', 'None', ''):
                continue

            # Build list of all alternate codes for this family
            all_codes = [current_code]

            if last_old_code and last_old_code not in ('nan', 'None', ''):
                all_codes.append(last_old_code)
                old_to_current[last_old_code] = current_code

            if original_code and original_code not in ('nan', 'None', '') and original_code != last_old_code:
                all_codes.append(original_code)
                old_to_current[original_code] = current_code

            # Store mappings
            if len(all_codes) > 1:
                current_to_old[current_code] = all_codes[1:]  # All except current
                all_codes_by_family[current_code] = all_codes

        _ALTERNATE_CODES_CACHE = {
            'current_to_old': current_to_old,
            'old_to_current': old_to_current,
            'all_codes_by_family': all_codes_by_family
        }

        return _ALTERNATE_CODES_CACHE

    except Exception as e:
        print(f"Error loading alternate codes: {str(e)}")
        _ALTERNATE_CODES_CACHE = {
            'current_to_old': current_to_old,
            'old_to_current': old_to_current,
            'all_codes_by_family': all_codes_by_family
        }
        return _ALTERNATE_CODES_CACHE


def get_current_code(material_code):
    """
    Get the current/active code for a given material code.

    Args:
        material_code: Any material code (current or old)

    Returns:
        Current material code, or original code if not found in mappings
    """
    mapping = load_alternate_codes_mapping()

    # If it's an old code, return the current code
    if material_code in mapping['old_to_current']:
        return mapping['old_to_current'][material_code]

    # Otherwise assume it's already the current code
    return material_code


def get_alternate_codes(material_code):
    """
    Get all alternate codes for a given material code.

    Args:
        material_code: Any material code (current or old)

    Returns:
        List of all alternate codes (including current), or [material_code] if no alternates
    """
    mapping = load_alternate_codes_mapping()

    # First normalize to current code
    current_code = get_current_code(material_code)

    # Get all codes in this family
    if current_code in mapping['all_codes_by_family']:
        return mapping['all_codes_by_family'][current_code]

    return [material_code]


def is_old_code(material_code):
    """
    Check if a material code is an old/obsolete code.

    Args:
        material_code: Material code to check

    Returns:
        Boolean indicating if this is an old code
    """
    mapping = load_alternate_codes_mapping()
    return material_code in mapping['old_to_current']


def has_alternate_codes(material_code):
    """
    Check if a material code has alternate codes.

    Args:
        material_code: Material code to check

    Returns:
        Boolean indicating if alternate codes exist
    """
    alternate_codes = get_alternate_codes(material_code)
    return len(alternate_codes) > 1


def normalize_material_codes(df, code_column='Material Number'):
    """
    Normalize all material codes in a dataframe to current codes.

    Args:
        df: DataFrame containing material codes
        code_column: Name of the column containing material codes

    Returns:
        DataFrame with normalized codes and additional columns:
        - {code_column}_current: Current code
        - {code_column}_original: Original code from data
        - has_alternate_codes: Boolean flag
        - is_old_code: Boolean flag
    """
    import pandas as pd

    if code_column not in df.columns:
        return df

    # Create a copy to avoid modifying original
    df = df.copy()

    # Store original code
    df[f'{code_column}_original'] = df[code_column]

    # Normalize to current code
    df[f'{code_column}_current'] = df[code_column].apply(get_current_code)

    # Add flags
    df['has_alternate_codes'] = df[code_column].apply(has_alternate_codes)
    df['is_old_code'] = df[code_column].apply(is_old_code)

    # Replace the main column with current code if auto_normalize is enabled
    if ALTERNATE_CODES_RULES['normalization']['auto_normalize']:
        df[code_column] = df[f'{code_column}_current']

    return df


def get_alternate_codes_summary():
    """
    Get summary statistics about alternate codes.

    Returns:
        Dictionary with summary metrics
    """
    mapping = load_alternate_codes_mapping()

    total_families = len(mapping['all_codes_by_family'])
    total_old_codes = len(mapping['old_to_current'])

    # Count families by number of codes
    codes_per_family = {}
    for current, all_codes in mapping['all_codes_by_family'].items():
        num_codes = len(all_codes)
        codes_per_family[num_codes] = codes_per_family.get(num_codes, 0) + 1

    return {
        'total_sku_families': total_families,
        'total_old_codes': total_old_codes,
        'total_unique_codes': total_families + total_old_codes,
        'families_with_2_codes': codes_per_family.get(2, 0),
        'families_with_3_codes': codes_per_family.get(3, 0),
        'families_with_4plus_codes': sum(v for k, v in codes_per_family.items() if k >= 4)
    }


# ===== DOCUMENTATION EXPORT =====

def export_business_rules_documentation(output_path="BUSINESS_RULES_DOCUMENTATION.md"):
    """
    Export all business rules to a markdown documentation file.

    Args:
        output_path: Path for the output markdown file
    """
    with open(output_path, 'w') as f:
        f.write("# Business Rules Documentation\n\n")
        f.write("Auto-generated documentation of all business rules and field definitions.\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("---\n\n")
        f.write("## Data Field Definitions\n\n")

        for file_name, file_info in DATA_FIELD_DEFINITIONS.items():
            f.write(f"### {file_name}\n\n")
            f.write(f"**Description:** {file_info['file_description']}\n\n")
            f.write("| Field Name | Data Type | Required | Description | Used For |\n")
            f.write("|------------|-----------|----------|-------------|----------|\n")

            for field_name, field_def in file_info['fields'].items():
                used_for = ", ".join(field_def.get('used_for', []))
                f.write(f"| {field_name} | {field_def['data_type']} | "
                       f"{field_def['required']} | {field_def['description']} | {used_for} |\n")
            f.write("\n")

        f.write("---\n\n")
        f.write("## Calculated Fields\n\n")

        for field_name, field_info in CALCULATED_FIELDS.items():
            f.write(f"### {field_info['name']}\n\n")
            f.write(f"**Formula:** `{field_info['formula']}`\n\n")
            f.write(f"**Description:** {field_info['description']}\n\n")

            if 'interpretation' in field_info:
                f.write("**Interpretation:**\n\n")
                for range_val, meaning in field_info['interpretation'].items():
                    f.write(f"- {range_val}: {meaning}\n")
                f.write("\n")

            if 'notes' in field_info:
                f.write(f"**Notes:** {field_info['notes']}\n\n")

        f.write("---\n\n")
        f.write("## Business Rule Configurations\n\n")

        f.write("### Inventory Rules\n\n")
        f.write(f"```python\n{INVENTORY_RULES}\n```\n\n")

        f.write("### Service Level Rules\n\n")
        f.write(f"```python\n{SERVICE_LEVEL_RULES}\n```\n\n")

        f.write("### Backorder Rules\n\n")
        f.write(f"```python\n{BACKORDER_RULES}\n```\n\n")

        f.write("### Currency Rules\n\n")
        f.write(f"```python\n{CURRENCY_RULES}\n```\n\n")

        f.write("### Storage Location Rules\n\n")
        f.write("**Description:** Storage location codes and their classifications\n\n")
        f.write("| Code | Description | Status | Category | Availability |\n")
        f.write("|------|-------------|--------|----------|-------------|\n")

        for code, info in STORAGE_LOCATION_RULES["locations"].items():
            f.write(f"| {code} | {info['description']} | {info['status']} | "
                   f"{info['category']} | {info['availability']} |\n")

        f.write("\n**Category Groupings:**\n\n")
        for category, codes in STORAGE_LOCATION_RULES["categories"].items():
            f.write(f"- **{category.replace('_', ' ').title()}**: {', '.join(codes)}\n")

        f.write("\n**Availability Definitions:**\n\n")
        for avail_type, definition in STORAGE_LOCATION_RULES["availability_mapping"].items():
            f.write(f"- **{avail_type.title()}**: {definition}\n")
        f.write("\n")

        # Alternate Codes Rules
        f.write("### Alternate Codes Rules\n\n")
        f.write("**Description:** Material code alternate/supersession mapping rules\n\n")
        f.write(f"```python\n{ALTERNATE_CODES_RULES}\n```\n\n")

        # Add alternate codes summary
        f.write("**Alternate Codes Summary:**\n\n")
        try:
            summary = get_alternate_codes_summary()
            f.write(f"- Total SKU Families: {summary['total_sku_families']}\n")
            f.write(f"- Total Old Codes: {summary['total_old_codes']}\n")
            f.write(f"- Families with 2 codes: {summary['families_with_2_codes']}\n")
            f.write(f"- Families with 3+ codes: {summary['families_with_3_codes']}\n\n")
        except Exception as e:
            f.write(f"_Could not load alternate codes summary: {str(e)}_\n\n")

        f.write("**Business Impact:**\n\n")
        f.write("- **Inventory Consolidation**: Automatically aggregates inventory across all alternate codes\n")
        f.write("- **Historical Demand**: Combines demand history from old and current codes for accurate forecasting\n")
        f.write("- **Backorder Alerts**: Flags backorders on old codes when inventory exists on current code\n")
        f.write("- **Code Migration**: Recommends updating orders from old codes to current codes\n")
        f.write("- **Reporting**: All reports consolidate data under current/active material codes\n\n")


if __name__ == "__main__":
    # Export documentation when run directly
    export_business_rules_documentation()
    print("Business rules documentation exported to BUSINESS_RULES_DOCUMENTATION.md")
