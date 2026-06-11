# Input Data Reference

How the test/input FHIR files are organized and how the files within a scenario
relate to one another. This complements the supplier's
`CDS_TestData_DocumentationFor05252026zip.pdf` (cited as "the supplier PDF" below)
and records the details verified directly against the fixtures in `test/input/`.

For *what the processor does* with these files, see
[`specs/001-mvp-fhir-processor/data-model.md`](../specs/001-mvp-fhir-processor/data-model.md)
(entities) and `research.md` D1/D2/D4b (identity, persistence, collisions).

---

## 1. Tree layout

```
test/input/
  <measure>/
    standard/              # patient qualifies for the Initial Population → eCR generated
      <scenario_id>/
        <scenario_id>.json            # collection Bundle  (the input data)
        MeasureReport_<uuid>.json     # expected evaluation result
        Bundle_<uuid>.json            # eCR message Bundle (submission unit)
    not-in-population/     # patient does NOT meet Initial Population → no eCR
      <scenario_id>/
        <scenario_id>.json            # collection Bundle  (the input data)
        MeasureReport_<uuid>.json     # all population counts = 0
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

## 2. The 'standard' set — three files, one patient

Each standard scenario is **three JSON files that describe the same patient
encounter from three angles**. The **Patient GUID is the spine** that ties them
together; every file refers to the same `Patient/<GUID>`.

```
        <scenario_id>.json                MeasureReport_<uuid>.json          Bundle_<uuid>.json
        (Bundle / collection)             (MeasureReport)                    (Bundle / message)
        ┌───────────────────────┐         ┌─────────────────────────┐        ┌───────────────────────────────┐
        │ Patient/<G>           │◄────────┤ subject → Patient/<G>   │        │ [0] MessageHeader             │
        │ Condition             │         │ measure → <canonical>   │        │       focus → Bundle/eicr-…   │
        │ Encounter             │◄┐       │ evaluatedResource[] ────┼──┐     │ [1] Bundle (type=document) ◄──┘
        │ Observation           │ └───────┼──► Encounter/Condition/ │  │     │       = the eICR; RE-CONTAINS  │
        │ Practitioner (shared) │         │     Observation GUIDs   │  └────►│         Patient + all input   │
        │ Organization (shared) │         │ populations: IP/Den/Num │        │         resources             │
        │ Location     (shared) │         │ measureScore            │        │ [2] Bundle (type=collection)  │
        └───────────────────────┘         └─────────────────────────┘        │       = wrapper around the    │
                  ▲                                                           │         MeasureReport         │
                  └────────────── same resource GUIDs reappear in [1] ────────┘                               
                                                                             └───────────────────────────────┘
```

### File 1 — `<scenario_id>.json` (the collection Bundle) — **the input data**
- `Bundle.type = "collection"`, **no `entry.request`** (not directly transactable;
  the processor converts it to a transaction of PUTs — see research.md D2).
- Always contains: **Patient, Condition, Encounter, Observation, Practitioner,
  Organization, Location.** May contain extras per scenario (CMS165
  `bulk_dial_high` adds a second `Condition` and a `Procedure` for dialysis).
- **Practitioner / Organization / Location are shared reference resources**: they
  reuse **identical GUIDs across scenarios and across the nested eICR** (see §4).
  *(The supplier PDF §3 omits these three resources entirely — see §5.)*

### File 2 — `MeasureReport_<uuid>.json` — **the expected evaluation result**
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

### File 3 — `Bundle_<uuid>.json` (the eCR message Bundle) — **the submission unit**
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

> ⚠️ **The nested document Bundle's `id` is NOT its identity.** It is a fixed,
> measure-named handle reused across patients
> (`eicr-report-ChronicDSDiabetesPoorControl`,
> `eicr-report-ChronicDSControllingBloodPressure`). The per-case identity lives in
> `Bundle.identifier` (a `urn:uuid`). Persisting it by `id` would overwrite across
> patients — the "landmine" guarded against in research.md **D4b**. Verified:
> two CMS122 patients share `id = eicr-report-ChronicDSDiabetesPoorControl` but
> differ in `Bundle.identifier`.

### How these three files were generated (inferred)

The three files are **sibling exports of one server state on a drajer/eCRNow stack**,
*not* one input that produced two outputs. The generation involves **two distinct
engines** that are easy to conflate because both use CQL:

| Engine | Role here | Produces |
|---|---|---|
| **eCQM measure-evaluation engine** — `$evaluate-measure` (HAPI/cqf-ruler clinical-reasoning, `fqm-execution`, …) running the CQF APHL [`chronic-ds`](http://fhir.org/guides/cqf/aphl/chronic-ds) measure content | Scores the patient against the `Measure` (IP/Den/Num/Excl, `measureScore`) | **File 2 — MeasureReport** |
| **eCRNow** ([drajer-health/eCRNow](https://github.com/drajer-health/eCRNow)) | eICR *triggering* (RCTC trigger codes via eRSD) and eICR *generation* — collects patient data with "Loading Queries" and packages it as a Public Health Case Report | **File 3 — eICR message Bundle**, with File 2 folded in as its second nested bundle |

Reconstructed flow:

```
patient clinical data on the drajer FHIR server (http://ecr.drajer.com/...)
        │
        ├──► eCQM engine ($evaluate-measure, chronic-ds Measure) ──► MeasureReport         (File 2)
        │
        └──► eCRNow (RCTC trigger → Loading Queries → eICR) ───────► eICR message Bundle    (File 3)
                                                                       └─ re-contains the patient
                                                                          resources + the MeasureReport
        │
        └──► export of the patient resources as-is ───────────────► collection Bundle      (File 1)
```

**Why two engines, not one.** eCRNow's scope is case *reporting*, not quality
*measurement*. It does embed a CQL / clinical-reasoning engine, but only for
**PlanDefinition / trigger evaluation** (deciding *whether and when* to report) — its
README exposes exactly one knob, `cql.enabled` "for PlanDefinition evaluation," and
makes **no** mention of `MeasureReport`, eCQM, or `$evaluate-measure` (verified against
the master README, 2026-06). Computing the population counts in File 2 is a *different*
use of CQL performed by a separate measure-evaluation engine. So "feed file 1 into
eCRNow, get files 2 and 3" conflates the two engines.

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
> The engine split and pipeline above are *inferred from the artifacts* (endpoints,
> `fullUrl`s, `Composition` type, measure canonical) plus eCRNow's public docs — not
> confirmed by the test-data supplier's own pipeline description.

---

## 3. The 'not-in-population' set — two files

When the patient fails Initial Population criteria, **no eCR is generated**, so the
message Bundle is absent:

- `<scenario_id>.json` — collection Bundle, **same structure** as the standard
  input (Patient/Condition/Encounter/Observation + shared refs).
- `MeasureReport_<uuid>.json` — **all population counts are 0**
  (`IP=0, Den=0, Num=0, DenExcl=0`); the patient is outside the measure.

The processor handles whatever files are present rather than enforcing the 3-vs-2
count (data-model.md, `ScenarioFolder`).

---

## 4. Cross-scenario GUID behavior (why it matters for persistence)

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

## 5. Deltas from the supplier PDF

Gaps/discrepancies between `CDS_TestData_DocumentationFor05252026zip.pdf` and the
actual fixtures, worth keeping in mind:

1. **Omitted shared resources.** PDF §3 lists Patient/Encounter/Condition/
   Observation/MedicationRequest/ServiceRequest/Procedure but **omits the
   Practitioner, Organization, and Location** that are always present and are the
   basis of the dedup design (§4).
2. **"Standard Folder (4 files)" vs. 3 here.** The 4th file is the **XML copy** of
   the eCR bundle ("Provided in both JSON and XML… identical content"). This repo
   keeps only the JSON files (3 per standard scenario).
3. **CMS2 / depression-screening** is documented in the PDF but has **no fixtures**
   in this repo (only CMS122 and CMS165, one sample folder each).
4. **Source typos** in the PDF: `controllabe-bp/` (→ `controllable-bp`) and
   `Bunlde_{uuid}.json` (→ `Bundle_{uuid}.json`).
5. The PDF's folder counts (365 / 528) describe the **full delivered package**, not
   the sample committed here.
