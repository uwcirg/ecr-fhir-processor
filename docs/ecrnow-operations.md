# eCRNow Operations

How **eCRNow** (drajer's electronic case reporting app) runs the KAR bundles that
produced our fixtures: what it accepts, how it schedules work, which files it writes,
and how to find a missing eICR. This is *upstream* of this repo. eCRNow is run by the
data supplier, not by `process.py`.

**Related docs (not repeated here):**

- [`input-data.md` → Two pipelines](input-data.md#two-pipelines-ecrnows-inputs-and-outputs-vs-processpys):
  how eCRNow's inputs and outputs relate to `process.py`'s, and the two meanings of "submit".
- [`input-data.md` → How these three files were generated](input-data.md#how-these-three-files-were-generated):
  the KAR contents, the PlanDefinition workflow
  (`start` → `check-reportable` → `evaluate-measure` → `report-ds` → `create-eicr` →
  `validate-eicr` → `submit-eicr`), and the Denominator > 0 reporting gate.
- [`input-data.md` → Upstream source and local edits](input-data.md#upstream-source-and-local-edits):
  where the KAR files came from
  ([`cqframework/aphl-chronic-ig`](https://github.com/cqframework/aphl-chronic-ig)) and
  how our copies differ.
- [eCRNow on GitHub](https://github.com/drajer-health/eCRNow): the source, and
  its own wiki and README for installation and configuration.

**Source basis.** The statements below were checked against the eCRNow source at tag
[`v4.0.4`](https://github.com/drajer-health/eCRNow/tree/v4.0.4), the version used to
produce the fixtures. Line links point to that tag. The repo has no `v4.0.5` tag, so
behavior in 4.0.5 is assumed to be the same but hasn't been checked.

---

## 1. What eCRNow requires of its inputs

eCRNow has three kinds of input. It checks the FHIR `Bundle.type` of the first two only,
and it doesn't run a FHIR validator on any of them. It configures no `FhirValidator` and
no `StrictErrorHandler`.

| Input | How it arrives | `Bundle.type` check | If the check fails |
|---|---|---|---|
| **KAR bundle** (e.g. [`kars-collection-diabetes-bundle…json`](kars-collection-diabetes-bundle.FromMultiCare.20261112.json)) | Loaded from the KAR directory at startup | Must be `collection` ([`KarParserImpl.java:420`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/service/impl/KarParserImpl.java#L420)) | The KAR is **skipped**, and only an error is logged (around [`:511`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/service/impl/KarParserImpl.java#L511)). Nothing fails visibly, so if a KAR seems to be ignored, check this first. |
| **Notification** (subscription notification for the `encounter-end` event) | Posted to eCRNow by the EHR | Must be `history` ([`SubscriptionUtils.java:109`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/utils/SubscriptionUtils.java#L109)) | `InvalidNotification` is thrown and the notification is rejected. |
| **Patient data** | Pulled by eCRNow from the EHR's FHIR API, using the KAR's `us-ph-fhirquerypattern-extension` query templates | None. The search results (`searchset` Bundles) are used without any check. | n/a |

eCRNow never receives File 1 (the collection Bundle) as an input. File 1 is a separate
export of the same EHR data that eCRNow queried (see
[Two pipelines](input-data.md#two-pipelines-ecrnows-inputs-and-outputs-vs-processpys)).

---

## 2. How a notification is processed

**Each notification (one patient, one encounter) runs on its own.** eCRNow doesn't
batch patients or wait for every patient to be evaluated before reporting. Each
encounter goes through the whole workflow by itself.

Within one notification, a related action either runs straight away or is scheduled for
later ([`BsaAction.executeRelatedActions`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/kar/model/BsaAction.java#L176)):

- **No `offsetDuration`:** the action runs **inline**, in the same thread and job as
  its parent.
- **Has an `offsetDuration`:** eCRNow creates a persistent timer
  ([`setupTimer`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/kar/model/BsaAction.java#L275)),
  and the action runs as a scheduled job for that notification only.

In our KARs, only `start → check-reportable` has an offset: 60 s locally, 24 h upstream
(see [local edits](input-data.md#upstream-source-and-local-edits)). So for each
encounter:

```
encounter-end notification
  └─ start ──(timer: 60 s)──► one scheduled job for this patient/encounter:
                               check-reportable → evaluate-measure → report-ds
                               → create-eicr → validate-eicr → submit-eicr   (all inline)
                               then: action outputs written to debug files (§3)
```

So when a MeasureReport (File 2) exists, the job for that encounter has already run
`report-ds`, and also `create-eicr` if the gate was met. There is no later batch phase
still to come.

**Throttling** (`enable.throttling`, `throttle.recheck.interval`, in minutes) only
delays a job when the server is busy. It doesn't change the order of actions or which
actions run.

**Off-hours** (in the Healthcare Setting) can move a timer to after hours, but only when
the KAR's offset has a `<=` comparator. Our KARs don't use one.

---

## 3. What eCRNow writes, and where

All of the files below are **debug output**. They are written only when
`save.debug.files=true` (the default), to the directory set by
**`bsa.output.directory`** in `application.properties`. eCRNow's main *output* is
`submit-eicr`'s transmission to public health. Saving files is a side effect.

| File name pattern | Contents | Written by |
|---|---|---|
| `TriggerQueryBundle_<patientId>_<notificationResourceId>.json` | The EHR resources gathered by the trigger check (`ckr-is-encounter-reportable`, a `check-trigger-codes` sub-action of `check-reportable`) | [`KarProcessingData.saveDataToFile`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/model/KarProcessingData.java#L841), called from [`CheckTriggerCodes`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/kar/action/CheckTriggerCodes.java#L65) |
| `MeasureReport_<id>.json` | `evaluate-measure`'s output, i.e. **File 2** | [`KarProcessorImpl.saveDataForDebug`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/service/impl/KarProcessorImpl.java#L147) → [`BsaServiceUtils.saveResourceToFile`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/utils/BsaServiceUtils.java#L592) |
| `Bundle_<id>.json` | `create-eicr`'s output, the eICR Bundle, i.e. **File 3** | Same as above. Every action output is written as `<ResourceType>_<id>.json` once the job finishes ([`:278`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/service/impl/KarProcessorImpl.java#L278)). |
| `create-report_<patientId>_<notificationResourceId>.json` and `.xml` | A second copy of the eICR, written when the report is created | [`CreateReport.java:125-146`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/kar/action/CreateReport.java#L125-L146) |

Notes:

- **`TriggerQueryBundle_*` files have no `Bundle.type`.** The dump is built with a bare
  `new Bundle()`, and only `entry` is ever set. They're diagnostic snapshots, not FHIR
  documents meant to be exchanged. Don't feed them to a validator or to `process.py`
  as they are.
- **`Bundle_*` looks like a name for input data, but here it's the eICR.** When files
  are gathered "by type", it's easy to collect only `MeasureReport_*` and miss these.
- `create-report_*` is named per patient and encounter, so a rerun of the same
  encounter overwrites it. `Bundle_<id>` files are named by resource id.
- **Database:** eCRNow keeps a `ph_messages_v2` table (`PublicHealthMessage`). In
  v4.0.4 the *payload* is saved there (`submitted_cda_data`) only for **CDA** reports
  ([`CreateReport.createPublicHealthMessageForCda`](https://github.com/drajer-health/eCRNow/blob/v4.0.4/src/main/java/com/drajer/bsa/kar/action/CreateReport.java#L182)).
  Our KARs produce a **FHIR** eICR, so don't count on finding File 3 in the database.

These files are **not** `process.py` inputs until someone copies them under
`input/`. Their names map to the fixture names as follows: `MeasureReport_<uuid>.json`
→ File 2, `Bundle_<uuid>.json` → File 3 (see
[Tree layout](input-data.md#2-tree-layout)).

---

## 4. Troubleshooting: MeasureReports exist but no eICR (File 3)

eICRs should exist for every MeasureReport whose **Denominator count is > 0**, because
that's the `report-ds` gate. A MeasureReport with all-zero counts (the
[not-in-population](input-data.md#4-the-not-in-population-set--two-files) case)
correctly has no eICR.

For an encounter whose MeasureReport has Denominator > 0, work through these steps:

1. **Look in `bsa.output.directory` itself**, not in a copy, for `Bundle_*.json` and
   `create-report_*` from the same time. If the MeasureReports reached a file share
   through a script or sync job, check whether it copies only `MeasureReport_*`.
2. **Search the eCRNow log** for that patient or encounter id:
   - `Writing data to file:` lists the full path of every file eCRNow wrote. This is
     the quickest way to find where `Bundle_*` went.
   - `Action may execute in future or Conditions not met` on `report-ds` or
     `create-eicr` means the gate didn't pass. The likely cause is that the
     MeasureReport wasn't passed on as `%measurereport` (local edit #3 in
     [Upstream source and local edits](input-data.md#upstream-source-and-local-edits)).
   - `No report created, hence nothing do` or `No Report creator for type` means
     `create-eicr` ran but produced nothing.
   - Errors from `validate-eicr` or `submit-eicr` don't remove the files. The files are
     written when the report is created and when the job finishes, whether or not
     submission succeeds.
3. **Check the receiving end.** `submit-eicr` sends the eICR to the public-health
   endpoint configured in eCRNow. If that is a test receiver you control, File 3 will
   be there as well.

---

## 5. Our Bundle.type requirements vs. eCRNow's

`process.py` asks more of its inputs than eCRNow asks of its own. For example, File 1
must be a `collection` Bundle. See the input shape rules in
[the constitution, Principle IV](../.specify/memory/constitution.md) and the
[known validation issues](../known-validation-issues.md). eCRNow's tolerance (§1) explains
why its debug output can't be counted on to meet those rules.
