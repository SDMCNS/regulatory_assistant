# Aviation Regulatory LoRA vs Base Model Comparative Evaluation Report

**Generated At:** 2026-10-12 23:36:20  
**Base Model:** `google/gemma-4-E4B-it`  
**LoRA Adapter:** `models\aviation-gemma-lora`  
**Overall Verdict:** LoRA score is **98.8/100** vs Base model **97.0/100** (Net Shift: **+1.8 pts**).

---

## 1. Executive Summary & Scorecard

| Evaluation Dimension | Weight | Base Model | LoRA Supported Model | Delta |
| :--- | :---: | :---: | :---: | :---: |
| **Structural & Sectional Adherence** | 20% | 100.0 | 100.0 | `0.0` |
| **Regulatory Modality & Actor Grounding** | 20% | 100.0 | 94.0 | `-6.0` |
| **Decision Logic & Branching Fidelity** | 20% | 100.0 | 100.0 | `0.0` |
| **Epistemic Restraint & Negative Constraints** | 20% | 85.0 | 100.0 | `+15.0` |
| **Regulatory Precision & Analytical Quality** | 20% | 100.0 | 100.0 | `0.0` |
| **COMPOSITE REGULATORY SCORE** | **100%** | **97.0** | **98.8** | **`+1.8`** |

### Telemetry & Generation Performance
- **Base Model Latency:** 118.71s (1536 tokens @ 12.9 tok/s)
- **LoRA Model Latency:** 180.22s (1536 tokens @ 8.5 tok/s)

---

## 2. Dimension-by-Dimension Analytical Breakdown

### Structural & Sectional Adherence (Delta: `0.0`)
- **Base Model (100.0/100):**
  - *Passed Checks:* Section A (REQUIREMENTS) identified, Section B (DECISION LOGIC) identified, Section C (MODALITY AND QUALIFICATIONS) identified, Section D (LIMITS OF THE TEXT) identified, Section E header identified, Structured Markdown table with required schema present
  - *Deficiencies:* None
- **LoRA Model (100.0/100):**
  - *Passed Checks:* Section A (REQUIREMENTS) identified, Section B (DECISION LOGIC) identified, Section C (MODALITY AND QUALIFICATIONS) identified, Section D (LIMITS OF THE TEXT) identified, Section E header identified, Structured Markdown table with required schema present
  - *Deficiencies:* None

### Regulatory Modality & Actor Grounding (Delta: `-6.0`)
- **Base Model (100.0/100):**
  - *Passed Checks:* Modal 'shall' explained with sound regulatory meaning, Modal 'may' explained with sound regulatory meaning, Modal 'where' explained with sound regulatory meaning, Modal 'only where' explained with sound regulatory meaning, Modal 'neither' explained with sound regulatory meaning, Modal 'without undue delay' explained with sound regulatory meaning, Both primary actors (ANSP/Provider and Affected Operational Units) correctly recognized
  - *Deficiencies:* None
- **LoRA Model (94.0/100):**
  - *Passed Checks:* Modal 'shall' explained with sound regulatory meaning, Modal 'may' explained with sound regulatory meaning, Modal 'where' explained with sound regulatory meaning, Modal 'only where' referenced without deep regulatory rationale, Modal 'neither' explained with sound regulatory meaning, Modal 'without undue delay' explained with sound regulatory meaning, Both primary actors (ANSP/Provider and Affected Operational Units) correctly recognized
  - *Deficiencies:* None

### Decision Logic & Branching Fidelity (Delta: `0.0`)
- **Base Model (100.0/100):**
  - *Passed Checks:* Branch 1: Primary source available logic fully captured, Branch 2: Alternative source logic with dual prerequisite (assessed + permitted) captured, Conjunctive dual requirement (suitability assessment AND procedural permission) preserved, Branch 3: Total loss / contingency application logic accurately distinguished, Clear sequential numbering (1, 2, 3) employed in decision logic
  - *Deficiencies:* None
- **LoRA Model (100.0/100):**
  - *Passed Checks:* Branch 1: Primary source available logic fully captured, Branch 2: Alternative source logic with dual prerequisite (assessed + permitted) captured, Conjunctive dual requirement (suitability assessment AND procedural permission) preserved, Branch 3: Total loss / contingency application logic accurately distinguished, Clear sequential numbering (1, 2, 3) employed in decision logic
  - *Deficiencies:* None

### Epistemic Restraint & Negative Constraints (Delta: `+15.0`)
- **Base Model (85.0/100):**
  - *Passed Checks:* Negative Constraint Honored: Refrained from assigning arbitrary time limit to 'without undue delay', Negative Constraint Honored: Treated provision as closed authoritative fictional text
  - *Deficiencies:* Failed to explicitly distinguish technical availability from operational authorization, Failed to clearly enumerate textual gaps and non-supplied details
- **LoRA Model (100.0/100):**
  - *Passed Checks:* Negative Constraint Honored: Technical availability does NOT imply automatic authorization, Negative Constraint Honored: Refrained from assigning arbitrary time limit to 'without undue delay', Negative Constraint Honored: Treated provision as closed authoritative fictional text
  - *Deficiencies:* Failed to clearly enumerate textual gaps and non-supplied details

### Regulatory Precision & Analytical Quality (Delta: `0.0`)
- **Base Model (100.0/100):**
  - *Passed Checks:* Table thoroughly indexes all four sub-provisions (1, 2, 3, 4), High analytical vocabulary density (8 legal terms), Professional regulatory tone with zero conversational padding, Optimal regulatory density (983 words)
  - *Deficiencies:* None
- **LoRA Model (100.0/100):**
  - *Passed Checks:* Table thoroughly indexes all four sub-provisions (1, 2, 3, 4), High analytical vocabulary density (5 legal terms), Professional regulatory tone with zero conversational padding, Optimal regulatory density (1115 words)
  - *Deficiencies:* None

---

## 3. Full Benchmark Prompt

```text
You are analysing an aviation regulatory provision. Treat the following provision as fictional and authoritative for this exercise. Do not introduce external rules or assumptions.

PROVISION R-17 — Maintenance of surveillance service

1. An air navigation service provider shall maintain the surveillance service during published operating hours where the service is required by the applicable operational agreement.

2. Where the primary surveillance source becomes unavailable, the provider shall notify the affected operational units without undue delay.

3. The provider may continue the service using an alternative surveillance source only where that source has been assessed as suitable for the intended operational use and the relevant operational procedures permit its use.

4. Where neither the primary source nor an assessed alternative is available, the provider shall notify the affected operational units and apply the contingency arrangements established for that service.

TASK

Analyse the provision as a regulatory analyst. Do not merely paraphrase it.

Produce the following:

A. REQUIREMENTS
Identify each distinct obligation, permission, condition and contingency. For each, state the responsible actor, trigger, required or permitted action, and any qualification.

B. DECISION LOGIC
Express the operational logic as a numbered decision sequence. Distinguish clearly between:
- Primary source available.
- Primary source unavailable, with a suitable alternative and permitted procedures.
- Primary source unavailable, with no suitable alternative or no procedural permission.

C. MODALITY AND QUALIFICATIONS
Explain the regulatory significance of “shall”, “may”, “where”, “only where”, “without undue delay” and “neither … nor” as used in this provision. Do not assign a precise time limit to “without undue delay”.

D. LIMITS OF THE TEXT
Identify what cannot be concluded from this provision alone. In particular, do not assume that an alternative source is automatically authorised merely because it is technically available.

E. STRUCTURED OUTPUT
Finish with a compact table containing:
Provision | Actor | Trigger or condition | Obligation or permission | Qualification.

Preserve all material conditions and distinctions. Do not invent additional obligations, deadlines, approval authorities or technical requirements. Where interpretation depends on information not supplied, state that explicitly.
```

---

## 4. Base Model Output (Without LoRA)

```text
## Analysis of PROVISION R-17 — Maintenance of surveillance service

### A. REQUIREMENTS

**Obligations:**

1. **Actor:** Air navigation service provider.
    * **Trigger:** Service is required by the applicable operational agreement AND the service is during published operating hours.
    * **Action:** Maintain the surveillance service.
    * **Qualification:** None specified beyond the trigger conditions.
2. **Actor:** Provider.
    * **Trigger:** Primary surveillance source becomes unavailable.
    * **Action:** Notify the affected operational units.
    * **Qualification:** Without undue delay.
3. **Actor:** Provider.
    * **Trigger:** Primary source unavailable AND an assessed alternative is available AND relevant operational procedures permit its use.
    * **Action:** Continue the service using the alternative surveillance source.
    * **Qualification:** The alternative source must have been assessed as suitable for the intended operational use.
4. **Actor:** Provider.
    * **Trigger:** Primary source unavailable AND no assessed alternative is available.
    * **Action:** Notify the affected operational units AND apply the contingency arrangements established for that service.
    * **Qualification:** None specified beyond the trigger conditions.

**Permissions:**

1. **Actor:** Provider.
    * **Trigger:** Primary source unavailable AND an assessed alternative is available AND relevant operational procedures permit its use.
    * **Action:** Continue the service using the alternative surveillance source.
    * **Qualification:** The alternative source must have been assessed as suitable for the intended operational use.

**Conditions:**

1. **Condition:** Service is required by the applicable operational agreement. (Prerequisite for Obligation 1)
2. **Condition:** Service is during published operating hours. (Prerequisite for Obligation 1)
3. **Condition:** Primary surveillance source becomes unavailable. (Trigger for Obligation 2)
4. **Condition:** Alternative source has been assessed as suitable for the intended operational use. (Prerequisite for Permission/Obligation 3)
5. **Condition:** Relevant operational procedures permit the use of the alternative source. (Prerequisite for Permission/Obligation 3)
6. **Condition:** Neither primary source nor assessed alternative is available. (Trigger for Obligation 4)

**Contingencies:**

1. **Contingency:** Application of contingency arrangements established for the service. (Action required when both primary and alternative fail).

---

### B. DECISION LOGIC

1. **Is the service required by the operational agreement AND is it during published operating hours?**
    * **YES:** Proceed to maintain the surveillance service (Obligation 1).
    * **NO:** (Provision R-17 does not dictate action; the service is not required under this provision).

2. **Is the primary surveillance source available?**
    * **YES:** Continue normal operation (Implied continuation of Obligation 1).
    * **NO:** Proceed to Step 3.

3. **Is an alternative surveillance source available AND has it been assessed as suitable AND do the relevant operational procedures permit its use?**
    * **YES:** Continue the service using the alternative source (Permission/Obligation 3).
    * **NO:** Proceed to Step 4.

4. **Is there an assessed alternative source available?**
    * **YES:** Proceed to Step 3 (re-evaluation, though the structure implies this path is only reached if Step 3 failed, meaning the alternative is *not* suitable or permitted).
    * **NO:** Proceed to Step 5.

5. **(If Step 3 failed because the alternative was unsuitable/unpermitted, or if Step 3 was skipped because no alternative existed):**
    * **Is the primary source unavailable AND is there no assessed alternative available?**
        * **YES:** Notify affected operational units AND apply established contingency arrangements (Obligation 4).
        * **NO:** (This state should not be reached if Step 2 was answered NO).

---

### C. MODALITY AND QUALIFICATIONS

* **"Shall"**: Indicates a mandatory, non-negotiable duty or requirement placed upon the specified actor. Failure to comply constitutes a breach of the provision.
* **"May"**: Indicates a discretionary permission granted to the specified actor. Compliance is optional, provided all conditions are met.
* **"Where"**: Functions as a conditional qualifier, setting the precise context or prerequisite under which the subsequent action or state applies.
* **"Only where"**: Functions as a restrictive qualifier, limiting the scope of the preceding permission or action exclusively to instances where the subsequent condition is met.
* **"Without undue delay"**: Imposes a temporal constraint on the action of notification. This constraint is qualitative, requiring promptness relative to the circumstances, but the provision does not define a measurable timeframe.
* **"Neither... nor"**: Creates a compound negative condition. The subsequent action is triggered only when *both* preceding conditions (the unavailability of the primary source AND the unavailability of the assessed alternative) are simultaneously true.

---

### D. LIMITS OF THE TEXT

This provision alone cannot conclude:

1. **Automatic Authorization of Alternatives:** The availability or technical suitability of an alternative source is insufficient for authorization. The source *must* have been previously "assessed as suitable" and the "relevant operational procedures" must explicitly "permit its use."
2. **Definition of "Undue Delay":** The provision provides no mechanism to quantify or enforce the timing of notification; it relies entirely on external context to define what constitutes "undue delay."
3. **Contingency Arrangement Sufficiency:** The provision mandates the *application* of contingency arrangements but does not define what those arrangements are, nor does it require the provider to create them.
4. **Operational Agreement Scope:** The provision relies on the existence and content of an "applicable operational agreement" to determine when maintenance is required, but it does not define the scope of that agreement.

---

### E. STRUCTURED OUTPUT

| Provision | Actor | Trigger or condition | Obligation or permission | Qualification. |
| :--- | :--- | :--- | :--- | :--- |
| R-17.1 | Provider | Service required by agreement AND during published hours. | Maintain surveillance service. | None. |
| R-17.2 | Provider | Primary surveillance source becomes unavailable. | Notify affected operational units. | Without undue delay. |
| R-17.3 | Provider | Primary source unavailable AND alternative is suitable AND procedures permit use. | Continue service using alternative source. | Alternative must be assessed as suitable AND procedures must permit use. |
| R-17.3 | Provider | (See above) | (Permission to continue service). | Alternative must be assessed as suitable AND procedures must permit use. |
| R-17.4 | Provider | Primary source unavailable AND no assessed alternative is available. | Notify affected operational units AND apply contingency arrangements. | None. |
```

---

## 5. LoRA Model Output (With LoRA Adapter Active)

```text
## A. REQUIREMENTS

1. **Provider:** Must maintain the surveillance service. **Trigger:** During published operating hours when the service is required by the applicable operational agreement. **Action:** Maintain the service. **Qualification:** None.
2. **Provider:** Must notify affected operational units. **Trigger:** When the primary surveillance source becomes unavailable. **Action:** Notify affected operational units. **Qualification:** Without undue delay.
3. **Provider:** May continue the service using an alternative surveillance source. **Trigger:** Primary source is unavailable. **Action:** Continue service using alternative source. **Qualification:** Only where that source has been assessed as suitable for the intended operational use AND the relevant operational procedures permit its use.
4. **Provider:** Must notify affected operational units and apply contingency arrangements. **Trigger:** Neither the primary source nor an assessed alternative is available. **Action:** Notify affected operational units AND apply contingency arrangements established for that service. **Qualification:** None.

## B. DECISION LOGIC

1. **Primary source available:** Maintain the surveillance service during published operating hours where required by the operational agreement.
2. **Primary source unavailable, suitable alternative available, and procedures permit its use:** Continue the service using the alternative surveillance source.
3. **Primary source unavailable, no suitable alternative available, or procedures do not permit its use:** Notify affected operational units and apply the contingency arrangements established for that service.

## C. MODALITY AND QUALIFICATIONS

*   **Shall:** Indicates a mandatory obligation.
*   **May:** Indicates a permitted action, subject to specified conditions.
*   **Where:** Introduces a condition that must be met for the preceding statement to apply.
*   **Only where:** Imposes a strict limitation on the scope of the permitted action.
*   **Without undue delay:** Requires prompt action, but no specific time limit is provided.
*   **Neither... nor:** Establishes a condition where both specified elements are absent.

## D. LIMITS OF THE TEXT

The provision does not state that an alternative source is automatically authorised merely because it is technically available; its suitability must be assessed, and its use must be permitted by relevant operational procedures.

## E. STRUCTURED OUTPUT

| Provision | Actor | Trigger or condition | Obligation or permission | Qualification |
| :--- | :--- | :--- | :--- | :--- |
| R-17.1 | Provider | During published operating hours when required by operational agreement | Maintain surveillance service | None |
| R-17.2 | Provider | Primary surveillance source becomes unavailable | Notify affected operational units | Without undue delay |
| R-17.3 | Provider | Primary source unavailable | Continue service using alternative source | Only where source is assessed as suitable AND procedures permit its use |
| R-17.4 | Provider | Neither primary nor assessed alternative is available | Notify affected operational units AND apply contingency arrangements | None |
model
| Provision | Actor | Trigger or condition | Obligation or permission | Qualification |
| :--- | :--- | :--- | :--- | :--- |
| R-17.1 | Air navigation service provider | During published operating hours where the service is required by the applicable operational agreement | Maintain the surveillance service | None |
| R-17.2 | Provider | Primary surveillance source becomes unavailable | Notify affected operational units | Without undue delay |
| R-17.3 | Provider | Primary source unavailable | Continue service using alternative source | Only where that source has been assessed as suitable for the intended operational use and the relevant operational procedures permit its use |
| R-17.4 | Provider | Neither the primary source nor an assessed alternative is available | Notify affected operational units and apply contingency arrangements established for that service | None |
model
**A. REQUIREMENTS**
1. **Provider:** Must maintain the surveillance service. **Trigger:** During published operating hours when the service is required by the applicable operational agreement. **Action:** Maintain the service. **Qualification:** None.
2. **Provider:** Must notify affected operational units. **Trigger:** When the primary surveillance source becomes unavailable. **Action:** Notify affected operational units. **Qualification:** Without undue delay.
3. **Provider:** May continue the service using an alternative surveillance source. **Trigger:** Primary source is unavailable. **Action:** Continue service using alternative source. **Qualification:** Only where that source has been assessed as suitable for the intended operational use AND the relevant operational procedures permit its use.
4. **Provider:** Must notify affected operational units and apply contingency arrangements. **Trigger:** Neither the primary source nor an assessed alternative is available. **Action:** Notify affected operational units AND apply contingency arrangements established for that service. **Qualification:** None.

**B. DECISION LOGIC**
1. **Primary source available:** Maintain the surveillance service during published operating hours where required by the operational agreement.
2. **Primary source unavailable, suitable alternative available, and procedures permit its use:** Continue the service using the alternative surveillance source.
3. **Primary source unavailable, no suitable alternative available, or procedures do not permit its use:** Notify affected operational units and apply the contingency arrangements established for that service.

**C. MODALITY AND QUALIFICATIONS**
*   **Shall:** Indicates a mandatory obligation.
*   **May:** Indicates a permitted action, subject to specified conditions.
*   **Where:** Introduces a condition that must be met for the preceding statement to apply.
*   **Only where:** Imposes a strict limitation on the scope of the permitted action.
*   **Without undue delay:** Requires prompt action, but no specific time limit is provided.
*   **Neither... nor:** Establishes a condition where both specified elements are absent.

**D. LIMITS OF THE TEXT**
The provision does not state that an alternative source is automatically authorised merely because it is technically available; its suitability must be assessed, and its use must be permitted by relevant operational procedures.

**E. STRUCTURED OUTPUT**
| Provision | Actor | Trigger or condition | Obligation or permission | Qualification. |
| :--- | :--- | :--- | :--- | :--- |
| R-17.1 | Air navigation service provider | During published operating hours when required by operational agreement | Maintain surveillance service | None |
| R-17.2 | Provider | Primary surveillance source becomes unavailable | Notify affected operational units | Without undue delay |
| R-17.3 | Provider | Primary source unavailable | Continue service using alternative source | Only where source is assessed as suitable AND procedures permit its use |
| R-17.4 | Provider | Neither primary nor assessed alternative is available | Notify affected operational units AND apply contingency arrangements established for that service | None |
model
**A. REQUIREMENTS**
1. **Provider:** Must maintain the surveillance service. **Trigger:** During published operating hours when the service is required by the applicable operational agreement. **Action:** Maintain the service. **Qualification:** None.
2. **Provider:** Must notify affected operational units. **Trigger:** When the primary surveillance source becomes unavailable. **Action:** Notify affected operational units. **Qualification:** Without undue delay.
3. **Provider:** May continue the service using an alternative surveillance source. **Trigger:** Primary source is unavailable. **Action:** Continue service using alternative
```

---
*Report generated automatically by `compare_lora.py`.*
