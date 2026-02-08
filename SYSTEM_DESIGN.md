# System Design & Tool Inventory
## ClaimGuardian: Technical Specification

**Version:** 1.0  
**Date:** 2024

---

## 1. Knowledge Sources

### 1.1 Vector Database Collections

ClaimGuardian uses a vector database for semantic search of policy documents, enabling the agent to find relevant policy clauses based on natural language queries.

#### Collection: `Homeowner_Policy_Standard_v2`
**Purpose:** Stores embeddings of standard homeowner insurance policy documents  
**Content:**
- Policy clauses and coverage descriptions
- Exclusions and limitations
- Deductible rules
- Claim filing requirements
- Coverage limits by category (dwelling, personal property, liability)

**Embedding Model:** `text-embedding-3-large` (OpenAI) or equivalent  
**Metadata Fields:**
- `policy_version`: "v2.0"
- `section`: Coverage section identifier (e.g., "Dwelling_Coverage", "Personal_Property")
- `clause_id`: Unique identifier for the policy clause
- `effective_date`: Policy effective date range
- `coverage_type`: Type of coverage (e.g., "Property", "Liability", "Additional_Living_Expenses")

**Query Pattern:**
- Semantic search for claim descriptions (e.g., "water damage from burst pipe")
- Retrieval of relevant exclusions (e.g., "flood damage exclusion")
- Coverage limit lookups by claim type

---

#### Collection: `Renter_Policy_Standard_v1`
**Purpose:** Stores embeddings of renter's insurance policy documents  
**Content:**
- Personal property coverage
- Liability coverage
- Loss of use coverage
- Policy exclusions specific to renters

**Metadata Fields:**
- `policy_version`: "v1.0"
- `section`: Coverage section identifier
- `clause_id`: Unique identifier
- `effective_date`: Policy effective date range
- `coverage_type`: Type of coverage

---

#### Collection: `Commercial_Property_Policy_v1`
**Purpose:** Stores embeddings of commercial property insurance policy documents  
**Content:**
- Business property coverage
- Business interruption coverage
- Liability coverage for commercial properties

**Metadata Fields:**
- `policy_version`: "v1.0"
- `section`: Coverage section identifier
- `clause_id`: Unique identifier
- `effective_date`: Policy effective date range
- `coverage_type`: Type of coverage

---

#### Collection: `Repair_Cost_Benchmarks`
**Purpose:** Stores embeddings of repair cost reference data for estimate validation  
**Content:**
- Average repair costs by damage type and severity
- Regional cost variations
- Material and labor cost benchmarks
- Historical repair estimate data

**Metadata Fields:**
- `damage_type`: Type of damage (e.g., "Water_Damage", "Fire_Damage", "Roof_Repair")
- `severity`: Damage severity level (e.g., "Minor", "Moderate", "Severe")
- `region`: Geographic region
- `cost_range_min`: Minimum expected cost
- `cost_range_max`: Maximum expected cost
- `last_updated`: Last update timestamp

---

### 1.2 SQL Database Tables

#### Table: `Policy`
**Purpose:** Stores policyholder policy information  
**Schema:**
```sql
CREATE TABLE Policy (
    policy_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    policy_type VARCHAR(50) NOT NULL,  -- 'Homeowner', 'Renter', 'Commercial'
    policy_version VARCHAR(20) NOT NULL,
    effective_date DATE NOT NULL,
    expiration_date DATE NOT NULL,
    coverage_dwelling DECIMAL(12,2),
    coverage_personal_property DECIMAL(12,2),
    coverage_liability DECIMAL(12,2),
    deductible DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- 'Active', 'Expired', 'Cancelled'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status)
);
```

**Usage:**
- Retrieve policy details by `policy_id`
- Check policy status and effective dates
- Get coverage limits and deductibles

---

#### Table: `Claim_History`
**Purpose:** Stores historical claim records for fraud detection and pattern analysis  
**Schema:**
```sql
CREATE TABLE Claim_History (
    claim_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    policy_id VARCHAR(50) NOT NULL,
    claim_type VARCHAR(50) NOT NULL,  -- 'Water_Damage', 'Fire', 'Theft', etc.
    claim_amount DECIMAL(12,2) NOT NULL,
    incident_date DATE NOT NULL,
    filed_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,  -- 'Approved', 'Rejected', 'Pending', 'Escalated'
    fraud_score DECIMAL(5,4),  -- 0.0000 to 1.0000
    decision_date DATE,
    adjuster_id VARCHAR(50),
    decision_rationale TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_policy_id (policy_id),
    INDEX idx_incident_date (incident_date),
    INDEX idx_status (status),
    INDEX idx_fraud_score (fraud_score)
);
```

**Usage:**
- Retrieve user's claim history for fraud pattern detection
- Analyze claim frequency and timing patterns
- Calculate fraud risk scores based on historical behavior
- Track claim approval/rejection rates

---

#### Table: `Claim_Submissions`
**Purpose:** Stores incoming claim submissions and their processing state  
**Schema:**
```sql
CREATE TABLE Claim_Submissions (
    submission_id VARCHAR(50) PRIMARY KEY,
    claim_id VARCHAR(50) UNIQUE,
    user_id VARCHAR(50) NOT NULL,
    policy_id VARCHAR(50) NOT NULL,
    claim_type VARCHAR(50) NOT NULL,
    incident_description TEXT NOT NULL,
    incident_date DATE NOT NULL,
    claim_amount DECIMAL(12,2) NOT NULL,
    repair_estimate_description TEXT,
    photos_urls JSON,  -- Array of photo URLs
    submission_status VARCHAR(20) NOT NULL,  -- 'Received', 'Processing', 'Auto_Approved', 'Auto_Rejected', 'Escalated', 'Completed'
    current_node VARCHAR(50),  -- Current LangGraph node
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_policy_id (policy_id),
    INDEX idx_submission_status (submission_status),
    INDEX idx_created_at (created_at)
);
```

**Usage:**
- Track claim submission lifecycle
- Store claim processing state for LangGraph state machine
- Monitor processing times and status

---

#### Table: `Policy_Exclusions`
**Purpose:** Stores policy-specific exclusions and limitations  
**Schema:**
```sql
CREATE TABLE Policy_Exclusions (
    exclusion_id VARCHAR(50) PRIMARY KEY,
    policy_id VARCHAR(50) NOT NULL,
    exclusion_type VARCHAR(50) NOT NULL,  -- 'Flood', 'Earthquake', 'Wear_And_Tear', etc.
    exclusion_description TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_policy_id (policy_id),
    INDEX idx_exclusion_type (exclusion_type)
);
```

**Usage:**
- Check if a claim type is excluded under the policy
- Validate claim against policy exclusions
- Support auto-rejection logic for excluded claims

---

#### Table: `Fraud_Indicators`
**Purpose:** Stores fraud detection model features and indicators  
**Schema:**
```sql
CREATE TABLE Fraud_Indicators (
    indicator_id VARCHAR(50) PRIMARY KEY,
    claim_id VARCHAR(50) NOT NULL,
    indicator_type VARCHAR(50) NOT NULL,  -- 'Claim_Frequency', 'Timing_Anomaly', 'Amount_Anomaly', etc.
    indicator_value DECIMAL(10,4),
    indicator_description TEXT,
    severity VARCHAR(20),  -- 'Low', 'Medium', 'High', 'Critical'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_claim_id (claim_id),
    INDEX idx_indicator_type (indicator_type),
    INDEX idx_severity (severity)
);
```

**Usage:**
- Store fraud detection model outputs
- Track specific fraud indicators for auditability
- Support fraud score calculation

---

## 2. Action Tools

The following Python tools are available to the ClaimGuardian agent for executing actions during claim processing.

### 2.1 Policy Query Tools

#### `query_policy(policy_id: str, claim_type: str = None) -> dict`
**Purpose:** Retrieves policy information including coverage limits, deductibles, and effective dates.

**Parameters:**
- `policy_id` (str, required): Unique identifier for the policy
- `claim_type` (str, optional): Type of claim (e.g., "Water_Damage", "Fire") for targeted policy section retrieval

**Returns:**
```python
{
    "policy_id": "POL-12345",
    "user_id": "USER-67890",
    "policy_type": "Homeowner",
    "policy_version": "v2.0",
    "effective_date": "2024-01-01",
    "expiration_date": "2025-01-01",
    "status": "Active",
    "coverage_dwelling": 500000.00,
    "coverage_personal_property": 250000.00,
    "coverage_liability": 300000.00,
    "deductible": 1000.00,
    "exclusions": [
        {
            "exclusion_type": "Flood",
            "exclusion_description": "Flood damage is excluded from coverage"
        }
    ]
}
```

**Error Handling:**
- Raises `PolicyNotFoundError` if policy_id does not exist
- Raises `PolicyExpiredError` if policy is expired or inactive

**Usage Context:** Called during initial claim validation to verify policy status and coverage.

---

#### `semantic_search_policy(query: str, policy_version: str = "v2.0", top_k: int = 5) -> list[dict]`
**Purpose:** Performs semantic search on policy documents to find relevant clauses based on natural language query.

**Parameters:**
- `query` (str, required): Natural language query describing the claim or policy question
- `policy_version` (str, optional): Policy version to search (default: "v2.0")
- `top_k` (int, optional): Number of top results to return (default: 5)

**Returns:**
```python
[
    {
        "clause_id": "CLAUSE-001",
        "section": "Dwelling_Coverage",
        "content": "Water damage from burst pipes is covered under dwelling coverage...",
        "relevance_score": 0.92,
        "coverage_type": "Property"
    },
    {
        "clause_id": "CLAUSE-002",
        "section": "Exclusions",
        "content": "Flood damage is excluded from coverage...",
        "relevance_score": 0.85,
        "coverage_type": "Exclusion"
    }
]
```

**Error Handling:**
- Raises `VectorDBError` if vector database connection fails
- Returns empty list if no relevant clauses found

**Usage Context:** Used to find relevant policy clauses when claim type is ambiguous or requires detailed policy interpretation.

---

### 2.2 Fraud Detection Tools

#### `calculate_fraud_score(user_id: str, claim_data: dict) -> dict`
**Purpose:** Calculates a fraud risk score for a claim based on user history, claim patterns, and anomaly detection.

**Parameters:**
- `user_id` (str, required): Unique identifier for the policyholder
- `claim_data` (dict, required): Claim information including:
  ```python
  {
      "claim_type": "Water_Damage",
      "claim_amount": 3500.00,
      "incident_date": "2024-03-15",
      "incident_description": "Burst pipe in kitchen",
      "repair_estimate_description": "Pipe replacement and water damage repair"
  }
  ```

**Returns:**
```python
{
    "fraud_score": 0.23,  # 0.0 (low risk) to 1.0 (high risk)
    "risk_level": "Low",  # "Low", "Medium", "High", "Critical"
    "indicators": [
        {
            "indicator_type": "Claim_Frequency",
            "severity": "Low",
            "description": "User has filed 2 claims in the past 12 months (within normal range)"
        },
        {
            "indicator_type": "Timing_Anomaly",
            "severity": "None",
            "description": "No timing anomalies detected"
        },
        {
            "indicator_type": "Amount_Anomaly",
            "severity": "Low",
            "description": "Claim amount is within expected range for water damage"
        }
    ],
    "recommendation": "Auto_Approve"  # "Auto_Approve", "Review", "Escalate"
}
```

**Error Handling:**
- Raises `UserNotFoundError` if user_id does not exist
- Raises `FraudModelError` if fraud detection model fails

**Usage Context:** Called during claim processing to assess fraud risk and determine if claim should be auto-approved or escalated.

---

#### `retrieve_claim_history(user_id: str, lookback_months: int = 24) -> list[dict]`
**Purpose:** Retrieves historical claim records for a user to support fraud pattern analysis.

**Parameters:**
- `user_id` (str, required): Unique identifier for the policyholder
- `lookback_months` (int, optional): Number of months to look back (default: 24)

**Returns:**
```python
[
    {
        "claim_id": "CLM-001",
        "claim_type": "Water_Damage",
        "claim_amount": 2800.00,
        "incident_date": "2023-06-10",
        "filed_date": "2023-06-12",
        "status": "Approved",
        "fraud_score": 0.15
    },
    {
        "claim_id": "CLM-002",
        "claim_type": "Theft",
        "claim_amount": 1500.00,
        "incident_date": "2023-11-20",
        "filed_date": "2023-11-22",
        "status": "Approved",
        "fraud_score": 0.18
    }
]
```

**Error Handling:**
- Returns empty list if no claim history found
- Raises `DatabaseError` if database query fails

**Usage Context:** Used by fraud detection algorithm to analyze claim patterns and frequency.

---

### 2.3 Estimate Validation Tools

#### `validate_repair_estimate(description: str, amount: float, damage_type: str, region: str = None) -> dict`
**Purpose:** Validates repair cost estimates against industry benchmarks and historical data.

**Parameters:**
- `description` (str, required): Description of the repair work
- `amount` (float, required): Estimated repair cost
- `damage_type` (str, required): Type of damage (e.g., "Water_Damage", "Fire", "Roof_Repair")
- `region` (str, optional): Geographic region for regional cost adjustments

**Returns:**
```python
{
    "is_valid": True,
    "validation_status": "Within_Range",  # "Within_Range", "Below_Range", "Above_Range", "Suspicious"
    "benchmark_min": 2500.00,
    "benchmark_max": 4500.00,
    "benchmark_median": 3500.00,
    "variance_percentage": 0.0,  # Percentage difference from median
    "confidence": 0.85,  # Confidence in validation (0.0 to 1.0)
    "recommendations": [
        "Estimate is within expected range for water damage repairs",
        "Labor and material costs align with regional averages"
    ],
    "flags": []  # List of any red flags (empty if none)
}
```

**Error Handling:**
- Raises `InvalidDamageTypeError` if damage_type is not recognized
- Returns `validation_status: "Unknown"` if insufficient benchmark data

**Usage Context:** Called to verify that repair estimates are reasonable before auto-approval.

---

### 2.4 Coverage Validation Tools

#### `check_coverage_limits(policy_id: str, claim_amount: float, claim_type: str) -> dict`
**Purpose:** Verifies that a claim amount is within policy coverage limits and calculates remaining coverage.

**Parameters:**
- `policy_id` (str, required): Unique identifier for the policy
- `claim_amount` (float, required): Amount being claimed
- `claim_type` (str, required): Type of claim to determine relevant coverage type

**Returns:**
```python
{
    "is_within_limits": True,
    "coverage_type": "Dwelling_Coverage",
    "coverage_limit": 500000.00,
    "claim_amount": 3500.00,
    "remaining_coverage": 496500.00,
    "deductible": 1000.00,
    "net_payout": 2500.00,  # claim_amount - deductible
    "violations": []  # List of coverage violations (empty if none)
}
```

**Error Handling:**
- Raises `PolicyNotFoundError` if policy_id does not exist
- Raises `InvalidClaimTypeError` if claim_type is not covered by policy

**Usage Context:** Called to ensure claim amount does not exceed coverage limits before approval.

---

#### `check_policy_exclusions(policy_id: str, claim_type: str) -> dict`
**Purpose:** Checks if a claim type is excluded under the policy.

**Parameters:**
- `policy_id` (str, required): Unique identifier for the policy
- `claim_type` (str, required): Type of claim to check

**Returns:**
```python
{
    "is_excluded": False,
    "exclusions": [],  # List of matching exclusions (empty if none)
    "exclusion_details": []
}
```

**Or if excluded:**
```python
{
    "is_excluded": True,
    "exclusions": [
        {
            "exclusion_type": "Flood",
            "exclusion_description": "Flood damage is excluded from coverage"
        }
    ],
    "exclusion_details": [
        "Claim type 'Flood_Damage' matches policy exclusion 'Flood'"
    ]
}
```

**Error Handling:**
- Raises `PolicyNotFoundError` if policy_id does not exist

**Usage Context:** Called early in processing to auto-reject claims that are clearly excluded.

---

### 2.5 Decision & Documentation Tools

#### `generate_decision_rationale(claim_data: dict, analysis_results: dict) -> str`
**Purpose:** Generates a human-readable explanation of the claim decision for transparency and auditability.

**Parameters:**
- `claim_data` (dict, required): Original claim submission data
- `analysis_results` (dict, required): Results from policy checks, fraud detection, and estimate validation

**Returns:**
```python
"Claim approved automatically. Policy is active and covers water damage. Claim amount ($3,500) is within coverage limits ($500,000 dwelling coverage). Fraud score is low (0.23). Repair estimate ($3,500) is within expected range for water damage repairs ($2,500-$4,500). Deductible ($1,000) applied. Net payout: $2,500."
```

**Usage Context:** Called before finalizing claim decision to create audit trail and user communication.

---

#### `log_claim_decision(claim_id: str, decision: str, rationale: str, processing_nodes: list[str]) -> bool`
**Purpose:** Logs the final claim decision and processing path for auditability.

**Parameters:**
- `claim_id` (str, required): Unique identifier for the claim
- `decision` (str, required): Final decision ("Auto_Approved", "Auto_Rejected", "Escalated")
- `rationale` (str, required): Decision rationale text
- `processing_nodes` (list[str], required): List of LangGraph nodes traversed during processing

**Returns:**
- `True` if logging successful, `False` otherwise

**Usage Context:** Called at the end of claim processing to maintain audit trail.

---

## 3. External API Integrations

### 3.1 Payment API
- **Endpoint:** `POST /api/v1/payments/initiate`
- **Purpose:** Initiate approved claim payouts
- **Authentication:** OAuth 2.0

### 3.2 Notification API
- **Endpoint:** `POST /api/v1/notifications/send`
- **Purpose:** Send status updates to policyholders
- **Channels:** Email, SMS, Push notifications

### 3.3 Escalation API
- **Endpoint:** `POST /api/v1/escalations/create`
- **Purpose:** Route complex claims to human adjuster queue
- **Payload:** Enriched claim context and analysis results

---

## 4. Tool Execution Constraints

- **Rate Limits:** Maximum 100 tool calls per claim processing session
- **Timeout:** Each tool call must complete within 5 seconds
- **Retry Logic:** Maximum 3 retries for transient failures
- **Error Handling:** All tools must return structured error responses (no exceptions)

---

**Document Owner:** Solutions Architecture Team  
**Last Updated:** 2024
