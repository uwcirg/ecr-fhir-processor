# Input Data Reference

How the test/input FHIR files are organized and how the files within a scenario
relate to one another. This complements the supplier's
`CDS_TestData_DocumentationFor05252026zip.pdf` (cited as "the supplier PDF" below)
and records the details verified directly against the fixtures in `test/input/`.

For *what the processor does* with these files, see
[`specs/001-mvp-fhir-processor/data-model.md`](../specs/001-mvp-fhir-processor/data-model.md)
(entities) and `research.md` D1/D2/D4b (identity, persistence, collisions).

---

## Two pipelines: eCRNow's inputs and outputs vs. `process.py`'s

Two separate systems handle this data, and each has its own inputs and outputs.
**This document's "input" means `process.py`'s input** (everything under
`test/input/`), unless it says *eCRNow input* or *eCRNow output*.

```
      ┌──────────────── eCRNow (upstream; run by the data supplier) ────────────────┐
      │ inputs:  KAR bundle (PlanDefinition + Measure + Libraries + ValueSets)       │
      │          encounter-end notifications                                         │
      │          patient data pulled from the EHR's FHIR API (the KAR's query        │
      │          patterns), never handed to eCRNow as a file                         │
      │ outputs: MeasureReport ─────────────────────────────────────► File 2        │
      │          eICR message Bundle ───────────────────────────────► File 3        │
      │            └─ also sent ("submit-eicr") to the public-health endpoint        │
      │               configured in eCRNow                                           │
      │          debug files (TriggerQueryBundle_*, create-report_*, …)              │
      └──────────────────────────────────────────────────────────────────────────────┘
      EHR / drajer FHIR server ── export of the patient's resources ─► File 1

      ┌──────────────── process.py (this repo) ─────────────────────────────────────┐
      │ inputs:  Files 1, 2 and 3 under test/input/ (or input/), plus config.json   │
      │ outputs: independent PUTs to the analytics FHIR server (Aidbox)             │
      │          the output/ mirror of what was (or, with --dry-run, would be) sent │
      │          log/ and the RunSummary                                            │
      └──────────────────────────────────────────────────────────────────────────────┘
```

| File | For eCRNow | For `process.py` |
|---|---|---|
| **1.** `<scenario_id>.json` (collection Bundle) | **Neither an input nor an output.** It's an export of the patient data on the drajer FHIR server, the data eCRNow *queried*. It's the closest thing we have to eCRNow's input. | Input |
| **2.** `MeasureReport_<uuid>.json` | **Output** of the KAR's `evaluate-measure` action | Input |
| **3.** `Bundle_<uuid>.json` (eICR message Bundle) | **Output** of `create-eicr` → `validate-eicr` → `submit-eicr` | Input |

**"Submit" means two different things.**
- **eCRNow submits** File 3 to a **public health agency** (the `submit-eicr` action;
  FHIR `$process-message`, REST, or Direct transport, as configured in eCRNow). That
  is the sense in which File 3 is a public-health *submission*. The fixtures don't
  record where it went: `MessageHeader.destination` is absent, and only the drajer
  `source`/`sender` are given.
- **`process.py` submits** (PUTs) Files 1–3 to **our analytics FHIR server**. That is
  a separate, downstream step, and our README and specs mean this sense.

The KAR bundles are covered in §3, "How these three files were generated". How
eCRNow runs them (what it requires of its inputs, per-encounter scheduling, the files
it writes to `bsa.output.directory`, and how to find a missing eICR) is covered in
[`ecrnow-operations.md`](ecrnow-operations.md). A file eCRNow writes isn't a
`process.py` input until someone places it under `input/`.

---

## 1. Patient populations (the reporting funnel)

Public-health researchers reading this data are usually computing **proportions** — a
sub-population over a larger one it sits inside. The populations below are the nested
cohorts those ratios are drawn from: **each is a subset of the one above it**, so *any*
band can act as the denominator for a band below it. For example, you might ask what
fraction of **Seen/Triggered Patients** reach the **Initial Population**, or what
fraction of the **Initial Population** lands in the **Numerator**. (The two bands
literally named *Denominator* and *Numerator* are just the CMS measure's *own* built-in
proportion; the nesting lets researchers frame others.) The terminology and diagram
come from APHL's *Triggering & Reporting Flow* — please reuse these names when referring
to the populations.

![Triggering & Reporting Flow — the patient-population funnel: Total Patient Population → Seen/Triggered Patients → Initial Population → Denominator → Numerator. The Seen/Triggered band and everything below it is "sent to Public Health Agencies (PHA)"; the Initial Population band and below is "our measure cohort + proportion".](images/TRAX.Patient.Pipeline.PerAPHL.2026.FromSlides.jpg)

| Population | Who it is | What data we hold | How to identify it in this repo |
|---|---|---|---|
| **Total Patient Population** | Anyone ever seen at the hospital. | *None for most of them.* We only hold the subset that meets the trigger criteria below — true for both the test fixtures **and** real data. | n/a |
| **Seen/Triggered Patients** | Those who had an encounter during the target time period **and** have a `Condition` in the measure's trigger value set (Diabetes for CMS122, Essential Hypertension for CMS165; see §3 "How these three files were generated"). | A FHIR **collection Bundle** (line-level patient/encounter data) **+ a MeasureReport** indicating which sub-population (below) the patient is in. | Every scenario folder under `test/input/` — both `standard/` **and** `not-in-population/`. |
| **Initial Population** | Triggered patients who *also* meet the Measure's additional filtering (age, encounter, and diagnosis criteria). | Everything above, **plus an eCR `Bundle`** (the eICR message eCRNow sends to public health) added alongside. | The `standard/` folders — the **three-file** set (§3). NIP folders are triggered but *fail* IP, so they get **no** eCR. *(Strictly, the eCR is gated on **Denominator count > 0**, not IP; for these measures Denominator = IP, so the result is the same. A patient with a Denominator Exclusion still gets an eCR.)* |
| **Denominator** | **Everyone** in the Initial Population. | (same artifacts as Initial Population) | The `denominator` population in the MeasureReport — set to `true`/`1` on **all** IP records. |
| **Numerator** | The subset of the Initial Population that **eCRNow determined matches the CMS measure's criteria**. | (same artifacts as Initial Population) | The `numerator` population in the MeasureReport set to `true`/`1`. |

All of these per-patient flags and counts are read from the **MeasureReport**, which is
first-class for every case and is the analytic spine for this data (§7). In the diagram,
everything **at or below Seen/Triggered Patients is sent to Public Health Agencies
(PHA)**, and the **Initial Population → Numerator** band is the CMS "measure cohort +
proportion."

---

## 2. Tree layout

```
test/input/
  <measure>/
    standard/              # patient qualifies for the Initial Population → eCR generated
      <scenario_id>/
        <scenario_id>.json            # File 1: collection Bundle (export of the patient's EHR data)
        MeasureReport_<uuid>.json     # File 2: eCRNow output, the measure evaluation result
        Bundle_<uuid>.json            # File 3: eCRNow output, the eICR message sent to public health
    not-in-population/     # patient does NOT meet Initial Population → no eCR
      <scenario_id>/
        <scenario_id>.json            # File 1: collection Bundle (export of the patient's EHR data)
        MeasureReport_<uuid>.json     # File 2: eCRNow output, all population counts = 0
# All files under test/input/ are process.py inputs (see "Two pipelines" above).
```

`measure` and `population` are **derived from the path**, not from file contents
(see `InputFile` in data-model.md). Measures present in this repo:

| Path segment            | CMS measure | Measure canonical (in the MeasureReport)                                                      |
|-------------------------|-------------|-----------------------------------------------------------------------------------------------|
| `poor-diabetic-control` | CMS122 — Diabetes HbA1c Poor Control (≥9%)   | `…/Measure/DiabetesHemoglobinA1cHbA1cPoorControl9FHIR\|0.0.002` |
| `controllable-bp`       | CMS165 — Controlling High Blood Pressure     | `…/Measure/ControllingHighBloodPressureFHIR\|0.0.002`          |

> The supplier PDF also documents **CMS2 — depression-screening**, and the
> processor's `measure` enum reserves `depression-screening`, but **no CMS2
> fixtures exist in this repo.** The repo carries one sample scenario per
> populated folder; the full supplier package is much larger (PDF cites 365
> CMS122 / 528 CMS165 folders).

---

## 3. The Initial Population set — three files, one patient

The `standard/` folders hold the **Initial Population** cases from §1 (triggered
patients who also met the Measure's filtering, so an eCR was generated). Each such
scenario is **three JSON files that describe the same patient encounter from three
angles**. The **Patient GUID is the spine** that ties them
together; every file refers to the same `Patient/<GUID>`.

```
        <scenario_id>.json         MeasureReport_<uuid>.json      Bundle_<uuid>.json  (eCR payload)
        (Bundle / collection)      (MeasureReport)                (Bundle / message)
        ┌───────────────────────┐  ┌─────────────────────────┐    ┌─────────────────────────────────────┐
        │ Patient/<G>           │  │ subject → Patient/<G>   │    │ [0] MessageHeader                   │
        │ Condition             │  │ measure → <canonical>   │    │       focus → Bundle/eicr-report-…  │
        │ Encounter             │  │ evaluatedResource[] ──► │    │ [1] Bundle (type=document) = eICR   │
        │ Observation           │  │   Encounter/Condition/  │    │   • Composition   ◄── NEW           │
        │ Practitioner (shared) │  │   Observation GUIDs     │    │     "Public Health Case Report",    │
        │ Organization (shared) │  │ populations: IP/Den/Num │    │     ~13 narrative sections          │
        │ Location     (shared) │  │ measureScore            │    │   • re-contains Patient + all input │
        └───────────────────────┘  └─────────────────────────┘    │     resources (LOWER-FIDELITY —     │
                                                                  │     see File 3 notes below)         │
                                                                  │ [2] Bundle (type=collection)        │
                                                                  │   = wrapper around the MeasureReport│
                                                                  └─────────────────────────────────────┘

        Spine: every file shares the same Patient/<G>, and the eICR + MeasureReport reuse the
        collection's resource GUIDs. [2]'s MeasureReport is byte-identical to the middle file;
        only the Composition in [1] is new (this repo will save it additionally as an independent resource).
```

### File 1 — `<scenario_id>.json` (the collection Bundle) — **the patient's clinical data**
*An export of the EHR-side data eCRNow queried. It is neither an eCRNow input nor an
eCRNow output, but it is the authoritative clinical source among the three (see File 3).*
- `Bundle.type = "collection"`, **no `entry.request`** (not directly transactable;
  the processor splits it into independent per-resource PUTs, never a `transaction`;
  see research.md D2).
- Always contains: **Patient, Condition, Encounter, Observation, Practitioner,
  Organization, Location.** May contain extras per scenario (CMS165
  `bulk_dial_high` adds a second `Condition` and a `Procedure` for dialysis).
- **Practitioner / Organization / Location are shared reference resources**: they
  reuse **identical GUIDs across scenarios and across the nested eICR** (see §5).
  *(The supplier PDF §3 omits these three resources entirely — see §6.)*

### File 2 — `MeasureReport_<uuid>.json` — **eCRNow output: the measure evaluation result**
*Produced by the KAR's `evaluate-measure` action. It's what eCRNow actually computed,
not an "expected" result to test against.*
- `subject → Patient/<same GUID>` as File 1.
- `measure →` the measure canonical URL + version (table above).
- `evaluatedResource[] →` the **same** Encounter / Condition / Observation GUIDs
  from File 1.
- `group[].population[]` carries the counts; `measureScore` may be present.
  Standard examples in this repo:

  | Scenario | IP | Den | Num | DenExcl |
  |---|---|---|---|---|
  | CMS122 `DENOM_HbA1c_7p5_GoodControl`      | 1 | 1 | 0 | 0 |
  | CMS122 `VAR_NUM_DM_CKD_Insulin_PoorControl` | 1 | 1 | 1 | 0 |
  | CMS165 `bulk_dial_high_00042`             | 1 | 1 | 0 | 1 |

### File 3 — `Bundle_<uuid>.json` (the eCR message Bundle) — **eCRNow output: the eICR message sent to public health**
*Produced by the KAR's `create-eicr` → `validate-eicr` → `submit-eicr` actions. It's the
unit eCRNow **submits to a public health agency**; that's a separate step from
`process.py` PUTting it to our analytics server (see "Two pipelines" above).*
- `Bundle.type = "message"`. The outer `Bundle.id` is a **per-case GUID** (matches
  the filename). Three entries:
  1. **`MessageHeader`** — `eventCoding = eicr-case-report-message`;
     `focus → Bundle/eicr-report-<measure>` (the document bundle below).
  2. **`Bundle` (type=`document`)** — the eICR. **Re-contains all of File 1's
     resources** (same GUIDs, including the shared Practitioner/Org/Location).
  3. **`Bundle` (type=`collection`)** — a thin wrapper whose single entry is the
     **MeasureReport** (the same evaluation as File 2).
- **This file is largely a superset of Files 1 + 2** — the same clinical content,
  repackaged for transport. (The processor persists it whole under its wrapper
  GUID; it does not unpack the nested document in MVP — research.md D2.)
- **What it genuinely adds:** the `MessageHeader` (transport/routing) and the eICR
  **`Composition`** — a "Public Health Case Report" (LOINC `55751-2`) with ~13
  narrative sections (Reason for Visit, Problem List, …). The nested **MeasureReport is
  byte-identical to File 2.**
- **What it degrades:** the eICR's nested clinical copies are **lower-fidelity** than
  File 1's — e.g. Observation `effectiveDateTime` loses time-of-day
  (`2025-02-10T09:10:00Z` → `…T00:00:00+00:00`), and `Patient.address.line` is
  double-JSON-encoded (`"221 Elm Street"` → `"[\"221 Elm Street\"]"`). **File 1 (the
  collection Bundle) is therefore the authoritative source for the clinical resources;**
  File 3's value is the Composition, not its embedded data.

> ⚠️ **The nested document Bundle's `id` is NOT its identity.** It is a fixed,
> measure-named handle reused across patients
> (`eicr-report-ChronicDSDiabetesPoorControl`,
> `eicr-report-ChronicDSControllingBloodPressure`). The per-case identity lives in
> `Bundle.identifier` (a `urn:uuid`). Persisting it by `id` would overwrite across
> patients — the "landmine" guarded against in research.md **D4b**. Verified:
> two CMS122 patients share `id = eicr-report-ChronicDSDiabetesPoorControl` but
> differ in `Bundle.identifier`.

### How these three files were generated

**Source:** the two **KARS knowledge bundles** that were loaded into **eCRNow 4.0.4**
to produce the fixtures (received from MultiCare 2026-11-12):
[`docs/kars-collection-diabetes-bundle.FromMultiCare.20261112.json`](kars-collection-diabetes-bundle.FromMultiCare.20261112.json) (CMS122) and
[`docs/kars-collection-bloodpressure-bundle.FromMultiCare.20261112.json`](kars-collection-bloodpressure-bundle.FromMultiCare.20261112.json) (CMS165).
*(Earlier versions of this section **inferred** a "two engines" split, with an
external eCQM engine making File 2. The KARS bundles contradict that inference; see
below.)*

The KARS bundles contain **no patient data**, so they do not define the files as
instances. They are the **specification eCRNow executes**. Each bundle is a
`collection` of 74 resources:

| Resource | CMS122 (diabetes) | CMS165 (blood pressure) |
|---|---|---|
| `PlanDefinition` (the reporting workflow) | `…/chronic-ds/PlanDefinition/ChronicDSDiabetesPoorControl` | `…/chronic-ds/PlanDefinition/ChronicDSControllingBloodPressure` |
| `Measure` (CQFM computable measure) | `…/Measure/DiabetesHemoglobinA1cHbA1cPoorControl9FHIR\|0.0.002` (CMS122v11) | `…/Measure/ControllingHighBloodPressureFHIR\|0.0.002` (CMS165v12) |
| `Library` (CQL + ELM) | 12 (measure logic, FHIRHelpers, FHIRCommon, SDE, hospice/palliative/frailty exclusions, …) | 12 (same pattern) |
| `ValueSet` (pre-expanded, no `compose`) | 60 | 60 |

The `Measure` canonicals and versions match the fixtures' `MeasureReport.measure`
exactly.

**The PlanDefinition workflow** (the same shape for both measures; `…` = measure-specific):

```
start               trigger: named-event "encounter-end"; check-reportable runs 60 s later
                    (upstream: 24 h; see "Upstream source and local edits" below)
 └► check-reportable  applicability: a Condition exists in the trigger ValueSet
     │                  CMS122: Diabetes               2.16.840.1.113883.3.464.1003.103.12.1001 (370 codes)
     │                  CMS165: Essential Hypertension 2.16.840.1.113883.3.464.1003.104.12.1011 (17 codes)
     └► evaluate-measure  definitionCanonical → the Measure above
         │               inputs: Patient, Condition, Encounter, MedicationRequest, Observation
         │                       (+ Procedure for CMS165)
         │               output: MeasureReport ─────────────────────────────────────► File 2
         └► report-ds     applicability: MeasureReport denominator count > 0
              ├ create-eicr    inputs: the same clinical data + the MeasureReport
              │                output id "eicr-report-<PlanDefinition name>"
              │                profile eicr-measurereport-bundle
              ├ validate-eicr  (CMS122 declares output profile eicr-document-bundle)
              └ submit-eicr    output profile eicr-document-bundle ───────────────► File 3
```

#### Upstream source and local edits

The KARS bundles are published in **[`cqframework/aphl-chronic-ig`](https://github.com/cqframework/aphl-chronic-ig)**,
the source repo of the APHL Chronic Disease Surveillance IG. That IG is built on
build.fhir.org as `cqf.aphl.chronic-ds`, at version **0.1.0** as of 2026-11.
The fixtures' Measure canonicals are still pinned at `|0.0.002`. Our two files are:

| Local file | Upstream file (branch `main`) |
|---|---|
| [`docs/kars-collection-diabetes-bundle.FromMultiCare.20261112.json`](kars-collection-diabetes-bundle.FromMultiCare.20261112.json) | `archive-2025/kars/kars-collection-diabetes-bundle.json` |
| [`docs/kars-collection-bloodpressure-bundle.FromMultiCare.20261112.json`](kars-collection-bloodpressure-bundle.FromMultiCare.20261112.json) | `archive-2025/kars/kars-collection-bloodpressure-bundle.json` |

The upstream folder also has `depression` (CMS2) and `seenpatients` bundles, plus
`transaction`-type versions of each. The repo includes `_refreshKarsBundles.sh`,
the script that assembles the bundles from the IG source. Every resource carries
`cqfm-softwaresystem → Device/cqf-tooling`, which shows that CQF tooling built them.

**Local edits (verified by diff against upstream, 2026-11-16).** Both files have the
same 74 resources as upstream, in the same order. Apart from the edits below they
are identical to upstream. The edits adapt the bundles for the eCRNow deployment.
Neither file says who made them (presumably MultiCare or drajer).

| # | Edit | Where | Effect |
|---|---|---|---|
| 1 | `start → check-reportable` delay changed from **24 h** to **60 s** | PlanDefinition `start.relatedAction.offsetDuration` | eCRNow checks reportability one minute after encounter-end instead of a day later. This is likely a change for testing or demos. |
| 2 | **`us-ph-fhirquerypattern-extension`** added, e.g. `Patient/{{context.patientId}}`, `Encounter/{{context.encounterId}}`, `Observation?patient=Patient/{{context.patientId}}`, `MedicationRequest?patient=…&intent=order` | PlanDefinition action inputs; the `dataRequirement`s of the Measure's `effective-data-requirements` and the Libraries | eCRNow's **query templates** ("Loading Queries"): the FHIR searches it runs against the source EHR to collect data. These decide what ends up in the eICR (File 3). |
| 3 | **`us-ph-relateddata-extension` = `"measurereport"`** added | `report-ds` input and `create-eicr`'s MeasureReport input | Links those inputs to `evaluate-measure`'s output, so the MeasureReport flows into the reporting gate and into the eICR. |
| 4 | Extra `us-ph-relateddata-extension` / `cqf-referencedEntity` entries | Two Libraries' `dataRequirement`s, **CMS165 bundle only** | Further context bindings (for example `Encounter/{{context.encounterId}}`). They aren't in the CMS122 bundle; why is unknown. |

What this establishes about each file:

| File | Defined by KARS? | Notes |
|---|---|---|
| **1. Collection Bundle** | **No, only indirectly.** | The PlanDefinition inputs and the Measure's contained `effective-data-requirements` Library list which resource types and ValueSets the logic reads (Patient, Condition, Encounter, Observation, Coverage, Procedure, MedicationRequest, …). Practitioner / Organization / Location are not mentioned. |
| **2. MeasureReport** | **Yes: its production and its structure.** | Produced by `evaluate-measure`. The Measure defines its shape: populations IP / Den / Num / DenExcl, **6 stratifiers** (ethnicity, payer, race, sex, age-group, food-insecurity-risk) and **8 supplemental data elements** (the same 6 plus age, state and postal code of residence). |
| **3. eICR message Bundle** | **Mostly.** | `create-eicr` → `submit-eicr` produce the nested eICR document Bundle. The PlanDefinition output id **`eicr-report-ChronicDSDiabetesPoorControl` / `eicr-report-ChronicDSControllingBloodPressure` is where the fixed, measure-named `Bundle.id` comes from** (the "landmine" above). The outer `message` Bundle and its `MessageHeader` are **not** modeled in the PlanDefinition; they presumably come from eCRNow's submit/transport layer. |

Resulting flow:

```
patient clinical data on the drajer FHIR server (http://ecr.drajer.com/...)
        │
        └──► eCRNow 4.0.4 running the KARS PlanDefinition
               encounter-end → trigger-ValueSet check → evaluate-measure ─► MeasureReport        (File 2)
                                                         └ Den > 0 → create/validate/submit eICR ─► eICR message Bundle (File 3)
                                                                       └─ re-contains the patient resources + the MeasureReport
        │
        └──► export of the patient resources as-is ─────────────────────► collection Bundle    (File 1)
```

**One pipeline, not two engines.** The measure evaluation is a step **inside** the
eCRNow-executed workflow, and its MeasureReport is a direct input to `create-eicr`.
So Files 2 and 3 come from a single eCRNow run. The KARS bundles do not show whether
eCRNow 4.0.4 evaluates the CQL itself or delegates `evaluate-measure` to a
clinical-reasoning service. Either way, eCRNow orchestrates it.

**Reporting gate.** The eICR is generated when **Denominator > 0**, not on Initial
Population membership. For CMS122/CMS165, Denominator = IP, so the two are
equivalent in practice. This also explains why CMS165 `bulk_dial_high`
(Den = 1, DenExcl = 1) still has an eICR.

> ⚠️ **Caveat — `<scenario_id>.json` is a drajer export, not a pristine input.**
> Every `entry.fullUrl` and absolute reference is a
> `http://ecr.drajer.com/secure/fhir-r4/fhir/...` URL, and the message Bundle's
> `MessageHeader.source.endpoint` / `sender` point at the same drajer server. So the
> collection Bundle is a **snapshot of resources that already lived on the drajer
> server**, not a clean hand-authored seed fed *into* the pipeline. The actual input
> was the underlying patient data on that server; all three files are exports of it.
>
> Those drajer absolute references are exactly what the processor must **not** rewrite
> (they are external by definition) but **should** WARNING-log — see research.md **D3**.
>
> The pipeline above comes from the KARS PlanDefinitions plus the artifacts
> themselves (endpoints, `fullUrl`s, `Composition` type, measure canonical). How
> File 1 was exported, and where the outer `MessageHeader` comes from, are still
> inferred.

---

## 4. The 'not-in-population' set — two files

These are **Seen/Triggered Patients who are *not* in the Initial Population** (§1).
When the patient fails Initial Population criteria, **no eCR is generated**, so the
message Bundle is absent:

- `<scenario_id>.json` — collection Bundle, **same structure** as the standard
  input (Patient/Condition/Encounter/Observation + shared refs).
- `MeasureReport_<uuid>.json` — **all population counts are 0**
  (`IP=0, Den=0, Num=0, DenExcl=0`); the patient is outside the measure.

The processor handles whatever files are present rather than enforcing the 3-vs-2
count (data-model.md, `ScenarioFolder`).

---

## 5. Cross-scenario GUID behavior (why it matters for persistence)

| Resource kind | GUID behavior | Consequence |
|---|---|---|
| Patient, Condition, Encounter, Observation, MeasureReport, outer message Bundle | **Unique per scenario** | Distinct server resources; safe to PUT by id |
| Practitioner, Organization, Location | **Identical GUID + identical content, reused everywhere** | PUT-by-id de-duplicates them — written once, updated (not duplicated) by later scenarios. *Desired.* |
| Nested eICR document Bundle | **Fixed measure-named `id`, reused across patients; identity in `Bundle.identifier`** | Must never be persisted by `id`; upsert by `identifier` if ever unpacked (research.md D4b) |

Verified example (CMS122 `GoodControl`): `Patient`, the `MeasureReport.subject`,
and the eICR's `Patient` all agree on `016788c3-…`; `Practitioner/b2360d5d-…`,
`Organization/380dcfda-…`, `Location/26bbd95f-…` are byte-identical in both the
collection bundle and the nested eICR.

---

## 6. Deltas from the supplier PDF

Gaps/discrepancies between `CDS_TestData_DocumentationFor05252026zip.pdf` and the
actual fixtures, worth keeping in mind:

1. **Omitted shared resources.** PDF §3 lists Patient/Encounter/Condition/
   Observation/MedicationRequest/ServiceRequest/Procedure but **omits the
   Practitioner, Organization, and Location** that are always present and are the
   basis of the dedup design (§5).
2. **"Standard Folder (4 files)" vs. 3 here.** The 4th file is the **XML copy** of
   the eCR bundle ("Provided in both JSON and XML… identical content"). This repo
   keeps only the JSON files (3 per standard scenario).
3. **CMS2 / depression-screening** is documented in the PDF but has **no fixtures**
   in this repo (only CMS122 and CMS165, one sample folder each).
4. **Source typos** in the PDF: `controllabe-bp/` (→ `controllable-bp`) and
   `Bunlde_{uuid}.json` (→ `Bundle_{uuid}.json`).
5. The PDF's folder counts (365 / 528) describe the **full delivered package**, not
   the sample committed here.
6. **The generating specification is not in the PDF.** The KARS knowledge bundles
   (PlanDefinition + Measure + Libraries + ValueSets) that eCRNow 4.0.4 executed
   were received separately. They are locally edited copies of bundles in
   `cqframework/aphl-chronic-ig` (§3, "Upstream source and local edits"). They also
   contain the `Measure|0.0.002` resources that the HL7 validator currently cannot
   resolve (see `known-validation-issues.md`).

---

## 7. Downstream consumer & analytics (Aidbox SQL-on-FHIR)

The primary consumer is a **state Department of Health**. The processor persists into
**Aidbox**; the DoH analytics team then authors **SQL-on-FHIR `ViewDefinition`s** to
flatten the stored FHIR resources into tables for the analytics team to consume.

Stakeholder framing (paraphrased): *"all the records as eCR payloads used to create the
measures' numerator and denominator"* — **plus the not-in-population cases.** Mapped to
this data:

- The **eCR payload is `Bundle_<uuid>.json`** (File 3) and exists **only for
  in-population** cases. It is the DoH-facing artifact, and the **`Composition`** (§3)
  is what they care about most. The reduced fidelity of the eICR's *nested clinical
  copies* (§3) is acceptable to this consumer.
- **NIP cases are in scope too**, but they have **no eCR payload** — they are
  represented by their (zero-count) **MeasureReport** + collection-bundle resources.

**Why the storage shape matters.** A SQL-on-FHIR `ViewDefinition` is rooted at **one
resource type** and flattens **first-class, individually-stored resources**; it cannot
reach into an opaque nested Bundle. Consequences:

- ✅ **MeasureReport is the analytic spine.** It is first-class for **every** case
  (in-pop *and* NIP), and carries `measure`, `group.population` (IP/Den/Num/Excl), and
  `subject` — one row per case, joinable to the clinical resources (also first-class,
  from the collection→transaction PUTs) by patient. The current persistence (research.md
  **D2**) already lands these SQL-on-FHIR-ready. This covers the num/den requirement
  *and* the NIP requirement.
- ✅ **The eICR `Composition` is promoted to first-class** (decided — spec **OQ-3 /
  FR-022**, research.md **D2b**). The message Bundle is still retained whole as the eCR
  payload, and the nested `Composition` is *additionally* persisted at `Composition/<guid>`
  so a `ViewDefinition` over `Composition` can flatten it. Verified safe across all three
  standard fixtures: the Composition's id is a GUID and **100% of its references resolve to
  the clean collection-bundle resources**.
- 🧨 **Only the Composition is promoted — not the eICR's clinical resources.** Those are
  degraded duplicates sharing GUIDs with the clean collection-bundle copies; re-persisting
  them would overwrite good analytics data and trip the `(resourceType, id)` collision
  guard (spec **FR-019**, research.md **D4b**). `MessageHeader` is also left nested — its
  `focus` points at the fixed-id document Bundle we deliberately don't persist standalone.
