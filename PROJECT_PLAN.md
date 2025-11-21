# POP Supply Chain Platform - Project Plan

## Executive Summary

This project plan outlines the development roadmap for creating a comprehensive, modular supply chain platform for EssilorLuxottica POP operations. The platform leverages existing data sources to build detailed supply chain modules that integrate seamlessly to provide end-to-end visibility.

**Current Status**: Foundation established with data loading pipeline and basic dashboard
**Target**: Modular, scalable platform with integrated supply chain modules

---

## Phase 1: Foundation & Current State (COMPLETED ✓)

### Achievements
- ✅ Data loading infrastructure (`data_loader.py`, `file_loader.py`)
- ✅ Basic dashboard UI with Streamlit
- ✅ Service Level, Backorder, and Inventory data pipelines
- ✅ Diagnostic and debugging tools
- ✅ Test infrastructure

### Current Data Sources
1. **ORDERS.csv** - Customer orders and backorder tracking
2. **DELIVERIES.csv** - Shipment and delivery records
3. **INVENTORY.csv** - Real-time stock levels
4. **Master Data.csv** - Product catalog with SKU metadata
5. **DOMESTIC INBOUND.csv** - Inbound logistics
6. **Domestic Vendor POs.csv** - Purchase order tracking

---

## Phase 2: Module Development (IN PROGRESS)

### Goal
Create standalone, interconnected modules that each serve a specific supply chain function while sharing data and integrating seamlessly.

### 2.1 Service Level Module (Priority: HIGH)
**Status**: Foundation exists, needs enhancement

**Objectives**:
- Track on-time delivery performance by customer, SKU, and time period
- Monitor order cycle times
- Identify delivery performance trends
- Alert on service level degradation

**Data Integration**:
- Primary: DELIVERIES.csv, ORDERS.csv
- Supporting: Master Data.csv
- Links to: Backorder Module (late orders), Inventory Module (stock availability)

**Key Features**:
```
✓ On-time delivery % calculation
✓ Customer-level performance tracking
✓ Monthly trend analysis
□ Real-time alerts for missed commitments
□ Root cause analysis for late deliveries
□ Customer satisfaction scoring
□ Predictive late delivery warnings
```

**Technical Tasks**:
- [ ] Enhance `pages/service_level_page.py` with advanced analytics
- [ ] Add drill-down capabilities (customer → order → line item)
- [ ] Implement alerting system for SLA breaches
- [ ] Create export templates for customer reporting
- [ ] Add comparison views (YoY, MoM)

---

### 2.2 Backorder Management Module (Priority: HIGH)
**Status**: Foundation exists, needs enhancement

**Objectives**:
- Visibility into all open backorders
- Aging analysis and prioritization
- Root cause identification
- Customer impact assessment

**Data Integration**:
- Primary: ORDERS.csv
- Supporting: Master Data.csv, INVENTORY.csv
- Links to: Inventory Module (stock availability), Inbound Module (incoming supply)

**Key Features**:
```
✓ Current backorder quantity tracking
✓ Aging analysis (0-7, 8-14, 15-30, 30+ days)
✓ Customer and SKU breakdowns
□ Fulfillment priority ranking
□ Expected resolution dates (linked to inbound POs)
□ Customer communication templates
□ Backorder root cause categorization
□ Auto-allocation when stock arrives
```

**Technical Tasks**:
- [ ] Create dedicated backorder page in new UI structure
- [ ] Implement priority scoring algorithm
- [ ] Link backorders to incoming POs for ETA calculation
- [ ] Build "what-if" scenarios (if X stock arrives, which orders fill?)
- [ ] Add workflow for backorder resolution tracking

---

### 2.3 Inventory Management Module (Priority: HIGH)
**Status**: ✅ COMPLETED - Fully Enhanced with Advanced Features

**Objectives**:
- Real-time inventory visibility with currency conversion
- ABC analysis for value-based prioritization
- Days-on-hand and turnover tracking
- Slow-moving and obsolete inventory identification
- Scrap opportunity analysis with adjustable thresholds
- Stock-out risk monitoring and alerts
- Category-level performance benchmarking
- Future-ready for historical trend analysis

**Data Integration**:
- Primary: INVENTORY.csv
- Supporting: DELIVERIES.csv (demand calculation), Master Data.csv (product attributes)
- Links to: Backorder Module (allocation), Service Level Module (fulfillment capability)
- Business Rules: Centralized in `business_rules.py` for maintainability

**Key Features**:
```
✓ Current stock levels by SKU
✓ Stock aggregation by SKU with pricing
✓ Days of inventory outstanding (DIO) calculation
✓ Inventory value tracking with USD/EUR currency conversion
✓ Movement classification (Fast/Normal/Slow/Very Slow/Obsolete/Dead Stock)
✓ ABC Analysis with Pareto visualization (80/15/5 rule)
✓ Stock-out risk alerts (Critical/Warning/Safe levels)
✓ Slow-moving inventory identification and analysis
✓ Scrap opportunity analysis with adjustable threshold (default: 2 years)
✓ Category benchmarking with DIO heat map
✓ Interactive filtering (category, movement class, ABC class, stock-out risk, DIO range)
✓ SKU search capability (partial match)
✓ DIO distribution visualization (7 age buckets)
✓ Movement classification pie chart
✓ ABC analysis Pareto chart
✓ Top 50 slow-moving items by value with ABC classification
✓ Detailed scrap candidate reporting with value breakdown
✓ Critical stock-out risk items highlighted
✓ Downloadable CSV exports for all analyses (currency-specific)
✓ Adjustable settings (scrap threshold, stock-out threshold, currency)
✓ Structure for future monthly inventory snapshots
□ Reorder point calculator - FUTURE ENHANCEMENT
□ Inventory optimization recommendations - FUTURE ENHANCEMENT
□ Multi-location inventory view - FUTURE ENHANCEMENT
□ Historical trend analysis (requires monthly snapshots) - FUTURE ENHANCEMENT
```

**Technical Tasks**:
- [x] Create comprehensive inventory page (`pages/inventory_page.py`)
- [x] Implement DIO calculation using historical delivery data
- [x] Build inventory movement classification system (via business_rules.py)
- [x] Create slow-moving/obsolescence identification logic
- [x] Develop scrap opportunity analysis section with adjustable threshold
- [x] Add interactive filters (category, movement class, ABC, risk, DIO range)
- [x] Implement SKU search functionality
- [x] Build DIO distribution chart with currency support
- [x] Create movement classification pie chart
- [x] Implement ABC analysis with Pareto chart
- [x] Add stock-out risk analysis section
- [x] Build category benchmarking heat map
- [x] Implement top slow-movers table with ABC classification
- [x] Add detailed scrap candidate list with downloads
- [x] Implement currency conversion (USD/EUR with 0.9 rate)
- [x] Create business_rules.py for centralized rule management
- [x] Add adjustable settings sidebar (currency, thresholds)
- [x] Set up placeholder structure for future monthly snapshots
- [ ] Add reorder point and EOQ calculations - FUTURE
- [ ] Create inventory optimization recommendations - FUTURE
- [ ] Multi-location inventory balancing logic - FUTURE
- [ ] Implement historical trend charts (once snapshot data available) - FUTURE

**Future Inventory Enhancements** (Priority: MEDIUM):
```
Planned enhancements for inventory module:

1. Reorder Point Calculator
   - Calculate safety stock based on lead time and demand variability
   - Flag items below reorder point
   - EOQ (Economic Order Quantity) calculations
   - Min/max inventory level recommendations

2. Inventory Optimization Recommendations
   - "What-if" scenarios: impact analysis of scrap decisions
   - Target stock level suggestions based on service level goals
   - Cost optimization (holding cost vs stock-out cost)
   - Automated replenishment suggestions

3. Multi-Location Inventory View
   - Break down inventory by warehouse/distribution center
   - Inter-location transfer recommendations
   - Location-specific DIO and ABC analysis
   - Stock balancing opportunities

4. Historical Trend Analysis
   - Monthly inventory snapshots tracking
   - DIO trend over time (improving/deteriorating)
   - Inventory value trend charts
   - Seasonal pattern detection
   - Movement classification migration tracking

5. Integration with Backorders
   - Cross-reference slow-movers with demand
   - Identify data quality issues (obsolete items on backorder)
   - Prioritize stock-out vs scrap decisions
```

---

### 2.4 User Data Upload & Management Module (Priority: HIGH)
**Status**: Planned - Not yet implemented

**Objectives**:
- Enable users to upload their own source data files
- Provide data validation and error checking
- Clear cached data and load fresh user-uploaded data
- Provide template files for each required data source
- Ensure data quality and consistency

**Data Sources Supported**:
1. **ORDERS.csv** - Customer orders and backorder tracking
2. **DELIVERIES.csv** - Shipment and delivery records
3. **INVENTORY.csv** - Real-time stock levels
4. **Master Data.csv** - Product catalog with SKU metadata
5. **DOMESTIC INBOUND.csv** - Inbound logistics (optional)
6. **Domestic Vendor POs.csv** - Purchase order tracking (optional)
7. **ALTERNATE_CODES.csv** - SKU alternate/legacy code mappings (optional)

**Key Features**:
```
□ File upload interface for each data source
□ Template export functionality (CSV templates with correct column headers)
□ Data validation on upload (column checks, data type validation)
□ Preview uploaded data before processing
□ Error reporting with specific row/column details
□ Clear cache and reload with user data
□ File size and format checking
□ Success/failure notifications
□ Data source status dashboard (which files loaded, when, row counts)
□ Rollback to default data option
□ Upload history and audit trail
```

**Template Export Specifications**:
```
Each template should include:
- All required column headers in correct order
- Data type hints (via sample row or comments)
- Required vs optional field indicators
- Example data rows (1-2 samples)
- Instructions/notes in header comment
- File naming convention guidance
```

**Validation Rules**:
```
1. ORDERS.csv:
   - Required columns: Orders Detail - Order Document Number, Item - SAP Model Code,
     Order Creation Date: Date, Original Customer Name, Orders - TOTAL Orders Qty,
     Orders - TOTAL To Be Delivered Qty, Orders - TOTAL Cancelled Qty
   - Date format: M/D/YY
   - Numeric fields: Orders Qty, To Be Delivered Qty, Cancelled Qty
   - No duplicate order line items (Order Number + SKU)

2. DELIVERIES.csv:
   - Required columns: Deliveries Detail - Order Document Number, Item - SAP Model Code,
     Delivery Creation Date: Date, Deliveries - TOTAL Goods Issue Qty
   - Date format: M/D/YY
   - Numeric fields: Goods Issue Qty
   - Delivery date must be >= order date (if joined)

3. INVENTORY.csv:
   - Required columns: Storage Location, Material Number, Free Qt, Last Purchase Price
   - Numeric fields: Free Qt, Last Purchase Price
   - No negative quantities
   - No duplicate SKU+Location combinations

4. Master Data.csv:
   - Required columns: Material Number, PLM: Level Classification 4, Activation Date (Code),
     PLM: PLM Current Status, PLM: Expiration Date
   - Date format: Activation (M/D/YY), Expiration (YYYYMMDD)
   - No duplicate Material Numbers
   - Activation date must be <= Today

5. ALTERNATE_CODES.csv:
   - Required columns: SAP Material Current, SAP Material Last Old Code,
     SAP Material Original Code
   - All codes must be valid strings
   - Current code cannot be blank
```

**Technical Tasks**:
- [ ] Create data upload page (`pages/data_upload_page.py`)
- [ ] Build file upload widgets for each data source
- [ ] Implement template export function with correct headers
- [ ] Create validation framework for each file type
- [ ] Build error reporting UI with detailed messages
- [ ] Add data preview functionality
- [ ] Implement cache clearing mechanism
- [ ] Create data source status dashboard
- [ ] Add rollback to default data option
- [ ] Build upload history tracking
- [ ] Add file size limits and format checking
- [ ] Implement session state management for uploaded files
- [ ] Create user documentation for upload process
- [ ] Add success/error notifications with actionable guidance

**User Interface Design**:
```
┌─ Data Upload & Management ─────────────────────┐
│                                                 │
│ 📥 Upload Data Sources                          │
│ ├─ Required Files (3/3 uploaded)               │
│ │  ✓ ORDERS.csv         [Replace] [Template]  │
│ │  ✓ DELIVERIES.csv     [Replace] [Template]  │
│ │  ✓ INVENTORY.csv      [Replace] [Template]  │
│ │  ✓ Master Data.csv    [Replace] [Template]  │
│ │                                              │
│ └─ Optional Files (1/3 uploaded)               │
│    ✓ ALTERNATE_CODES.csv [Replace] [Template]  │
│    ○ DOMESTIC INBOUND.csv  [Upload] [Template] │
│    ○ Domestic Vendor POs   [Upload] [Template] │
│                                                 │
│ 📊 Data Status                                  │
│ ├─ ORDERS: 45,231 rows | Last updated: 2025-11-21 14:32 │
│ ├─ DELIVERIES: 123,456 rows | Last updated: 2025-11-21 14:32 │
│ ├─ INVENTORY: 8,942 rows | Last updated: 2025-11-21 14:32 │
│ └─ Master Data: 12,384 rows | Last updated: 2025-11-21 14:32 │
│                                                 │
│ ⚙️ Actions                                       │
│ [🔄 Refresh All Data] [🗑️ Clear Cache]        │
│ [📥 Download All Templates] [↩️ Restore Defaults] │
│                                                 │
│ 📜 Upload History (Last 10)                     │
│ └─ Table with: Timestamp, File, User, Status, Rows │
└─────────────────────────────────────────────────┘
```

**Integration**:
- Add to main dashboard navigation as "📤 Data Management"
- Link from sidebar "Quick Actions" section
- Integrate with existing data_loader.py infrastructure
- Use file_loader.py safe_read_csv with session state

---

### 2.5 Inbound Logistics Module (Priority: MEDIUM)
**Status**: Data sources available, module needs creation

**Objectives**:
- Track purchase orders from creation to receipt
- Monitor supplier performance
- Calculate and track lead times
- Manage domestic inbound shipments

**Data Integration**:
- Primary: Domestic Vendor POs.csv, DOMESTIC INBOUND.csv
- Supporting: INVENTORY.csv (receipts), Master Data.csv
- Links to: Backorder Module (expected relief), Inventory Module (incoming stock)

**Key Features**:
```
□ PO tracking (open, in-transit, received)
□ Supplier on-time delivery metrics
□ Lead time analysis by supplier and SKU
□ Receipt variance tracking (ordered vs received)
□ Inbound shipment status
□ Supplier scorecarding
□ PO aging and expedite recommendations
□ Automated ETA updates for backorders
```

**Technical Tasks**:
- [ ] Create data loader for Vendor PO and Inbound data
- [ ] Build inbound logistics page (`pages/inbound_page.py`)
- [ ] Implement supplier performance metrics
- [ ] Create PO tracking workflow
- [ ] Link incoming POs to backorder relief dates
- [ ] Build supplier scorecard with OTIF metrics

---

### 2.6 Demand Forecasting Module (Priority: MEDIUM)
**Status**: Placeholder exists, needs full implementation

**Objectives**:
- Forecast future demand by SKU
- Support inventory planning
- Identify seasonal trends
- Enable proactive procurement

**Data Integration**:
- Primary: ORDERS.csv, DELIVERIES.csv (historical demand)
- Supporting: Master Data.csv (product groupings)
- Links to: Inventory Module (planning), Inbound Module (procurement)

**Key Features**:
```
□ Historical demand analysis
□ Trend and seasonality detection
□ Statistical forecasting (moving average, exponential smoothing)
□ ML-based forecasting (optional)
□ Forecast accuracy tracking
□ Demand variability metrics
□ New product ramp forecasting
□ Promotional impact modeling
```

**Technical Tasks**:
- [ ] Build historical demand aggregation pipeline
- [ ] Implement basic forecasting algorithms
- [ ] Create forecast visualization page
- [ ] Add forecast vs actual comparison
- [ ] Integrate forecast into inventory planning
- [ ] Build forecast accuracy dashboard

---

### 2.7 Executive Overview Module (Priority: HIGH)
**Status**: Basic implementation exists, needs enhancement

**Objectives**:
- Single-pane-of-glass view of supply chain health
- Key KPIs across all modules
- Exception highlighting and alerts
- Executive-level reporting

**Data Integration**:
- Aggregated data from all modules
- Cross-module insights

**Key Features**:
```
✓ High-level KPI cards
✓ Basic performance charts
□ Supply chain health score
□ Critical alerts dashboard
□ Executive summary reports
□ Trend analysis across modules
□ Custom KPI builder
□ Goal tracking and variance
```

**Technical Tasks**:
- [ ] Enhance overview page with health scoring
- [ ] Implement cross-module alerts
- [ ] Create executive report generator
- [ ] Build customizable KPI dashboard
- [ ] Add goal-setting and tracking

---

## Phase 3: Module Integration & Workflows

### 3.1 Inter-Module Data Flows
**Goal**: Enable modules to share data and trigger actions

**Integration Points**:
1. **Backorder → Inbound**: Link backorders to expected PO receipts for ETA
2. **Inbound → Inventory**: Auto-update inventory on receipt
3. **Inventory → Backorder**: Auto-allocate stock to backorders
4. **Service Level → Backorder**: Identify late orders that became backorders
5. **Forecast → Inventory**: Feed forecast into replenishment planning
6. **Forecast → Inbound**: Generate procurement recommendations

**Technical Approach**:
- Shared data models in `data_loader.py`
- Event system for cross-module triggers
- Centralized state management
- API layer for module communication

---

### 3.2 Workflow Automation
**Goal**: Automate common supply chain workflows

**Priority Workflows**:
1. **Backorder Resolution**
   - Detect incoming stock
   - Prioritize and allocate to backorders
   - Generate pick lists
   - Update customer ETA

2. **Stock-Out Prevention**
   - Monitor inventory vs forecast
   - Alert when approaching reorder point
   - Auto-generate procurement recommendations
   - Track PO until receipt

3. **Service Level Recovery**
   - Detect late orders
   - Identify root causes (inventory, supplier delay)
   - Recommend corrective actions
   - Track to resolution

**Technical Tasks**:
- [ ] Build workflow engine
- [ ] Create rule-based automation system
- [ ] Implement notification framework
- [ ] Build workflow monitoring dashboard

---

## Phase 4: Advanced Features

### 4.1 Real-Time Data Integration
- Database connectivity (SQL Server/PostgreSQL)
- Automated data refresh
- Change data capture (CDC)
- Real-time alerting

### 4.2 Advanced Analytics
- Machine learning models for demand forecasting
- Anomaly detection across all modules
- Optimization algorithms (inventory, allocation)
- Simulation and scenario planning

### 4.3 Collaboration Features
- User roles and permissions
- Comments and annotations
- Shared reports and dashboards
- Task assignment and tracking

### 4.4 Mobile & API Access
- Mobile-responsive UI
- REST API for external integrations
- Mobile app for field operations
- Webhook support for event notifications

---

## Implementation Strategy

### Architecture Principles
1. **Modularity**: Each module is self-contained with clear interfaces
2. **Data-Driven**: All modules share common data layer
3. **Scalability**: Design for growth in data volume and user base
4. **Maintainability**: Clean code, comprehensive tests, clear documentation
5. **User-Centric**: Simple UI, easy navigation, actionable insights

### Development Approach
1. **Iterative**: Build modules incrementally, release early and often
2. **Test-Driven**: Write tests before/during feature development
3. **User Feedback**: Engage supply chain team throughout development
4. **Documentation**: Keep technical and user docs up to date

### Code Organization
```
POP_Supply_Chain/
├── data_loader.py          # Centralized data loading
├── file_loader.py          # File I/O utilities
├── utils.py                # Shared utilities
├── ui_components.py        # Reusable UI components
├── dashboard_simple.py     # Main application entry
├── pages/                  # Module pages
│   ├── overview_page.py
│   ├── service_level_page.py
│   ├── backorder_page.py
│   ├── inventory_page.py
│   ├── inbound_page.py
│   └── forecast_page.py
├── modules/                # Business logic modules
│   ├── service_level.py
│   ├── backorder.py
│   ├── inventory.py
│   ├── inbound.py
│   └── forecast.py
├── workflows/              # Automated workflows
│   ├── workflow_engine.py
│   └── rules.py
├── tests/                  # Comprehensive test suite
│   ├── conftest.py
│   ├── test_data_loaders.py
│   ├── test_modules.py
│   └── test_workflows.py
└── Data/                   # Source data files
```

---

## Success Metrics

### Module Completion Criteria
Each module is considered complete when it has:
- [ ] Full data pipeline implementation
- [ ] Comprehensive UI page
- [ ] Core features implemented (80%+ of planned)
- [ ] Unit and integration tests (>80% coverage)
- [ ] User documentation
- [ ] Performance validated (< 3 sec load time)

### Platform Success Metrics
- **Adoption**: 90%+ of supply chain team using platform weekly
- **Data Quality**: <1% data errors, 100% data source coverage
- **Performance**: Dashboard loads in <5 seconds
- **Reliability**: 99%+ uptime
- **User Satisfaction**: >4/5 average rating
- **Business Impact**: Measurable improvements in KPIs (service level, backorder reduction, inventory turnover)

---

## Timeline Estimate

### Phase 2: Module Development (8-12 weeks)
- Service Level enhancement: 1-2 weeks
- Backorder enhancement: 1-2 weeks
- Inventory development: 2-3 weeks
- Inbound development: 2-3 weeks
- Forecast development: 2-3 weeks
- Overview enhancement: 1 week

### Phase 3: Integration (4-6 weeks)
- Inter-module data flows: 2-3 weeks
- Workflow automation: 2-3 weeks

### Phase 4: Advanced Features (8-12 weeks)
- Real-time integration: 2-3 weeks
- Advanced analytics: 3-4 weeks
- Collaboration features: 2-3 weeks
- Mobile & API: 2-3 weeks

**Total Estimated Duration**: 20-30 weeks (5-7 months)

*Note: Timeline assumes single developer working full-time. Adjust for team size and part-time work.*

---

## Next Steps (Immediate)

### Week 1-2: Complete Simplified UI Infrastructure
- [x] Create modular UI components (`ui_components.py`)
- [x] Build page templates (overview, service level)
- [x] Implement navigation system
- [x] Complete inventory page with advanced features
- [x] Create business rules documentation system
- [ ] Complete remaining page stubs (backorder, inbound, forecast)
- [ ] User testing of new UI structure

### Week 3-4: Enhance Service Level Module
- [ ] Add drill-down capabilities
- [ ] Implement alerting system
- [ ] Create export functionality
- [ ] Add comparison views
- [ ] Write comprehensive tests

### Week 5-6: Complete Backorder Module
- [ ] Build full backorder page
- [ ] Implement priority ranking
- [ ] Link to inbound for ETAs
- [ ] Add resolution workflow
- [ ] Create customer communication templates

---

## Risk Management

### Technical Risks
- **Data Quality Issues**: Mitigate with robust validation and error handling
- **Performance with Large Datasets**: Implement caching, optimize queries
- **Integration Complexity**: Use clear interfaces, comprehensive testing

### Business Risks
- **User Adoption**: Involve users early, provide training, demonstrate value
- **Changing Requirements**: Use agile approach, modular design
- **Resource Constraints**: Prioritize high-value features, incremental delivery

---

## Conclusion

This project plan provides a roadmap for transforming the POP Supply Chain Dashboard into a comprehensive, integrated platform. By focusing on modular development, data integration, and user-centric design, we will deliver a powerful tool that provides end-to-end supply chain visibility and enables data-driven decision making.

The modular architecture ensures that each component can be developed, tested, and deployed independently while still contributing to the unified platform vision. This approach allows for flexibility, rapid iteration, and continuous value delivery to the supply chain team.

**Let's build an exceptional supply chain platform together!**
