# arena-1: descending-neuron inventory

Status: **inventory** for `arena-1` of the accepted
[DN-arena ADR](adr/adr-dn-arena.md) (Gianluca Mazza, 2026-10-19). This document
names MaleCNS v1.0 bodyIds and sides for the ADR's decoder types. It does not
choose a gain, write a lock, run a fixture, or edit
`validation/evidence.yaml`, `validation/motor_map.yaml`, `closedloop.ARMS` or
`flymsg.closedloop/v1`.

Required this milestone: DNa01, DNa02, oDN1. Listed only, for a later decoder
version: MDN and DNp01.

## Result

The three required types each have a unique traced MaleCNS identity. DNa01 and
DNa02 match the `type` column exactly. oDN1 is not a `type` or `instance`
token; the same annotation table attaches the official synonym
`Sapkal 2024: oDN1` to the two traced `DNg97` neurons and to no other body.
MDN and DNp01 are listed only. **No gain is chosen.** Because every required
type is mapped, this milestone does not stop on identity. `arena-2` is still a
later reviewed PR.

| Type  | This milestone                        | Status | MaleCNS `type` | bodyId | Side | Query                                   |
| ----- | ------------------------------------- | ------ | -------------- | ------ | ---- | --------------------------------------- |
| DNa01 | required (steering)                   | mapped | DNa01          | 10442  | L    | `type == "DNa01"`                       |
| DNa01 | required (steering)                   | mapped | DNa01          | 10760  | R    | `type == "DNa01"`                       |
| DNa02 | required (steering)                   | mapped | DNa02          | 523769 | L    | `type == "DNa02"`                       |
| DNa02 | required (steering)                   | mapped | DNa02          | 10360  | R    | `type == "DNa02"`                       |
| oDN1  | required (forward)                    | mapped | DNg97          | 13805  | L    | `synonyms` contains `Sapkal 2024: oDN1` |
| oDN1  | required (forward)                    | mapped | DNg97          | 230783 | R    | `synonyms` contains `Sapkal 2024: oDN1` |
| MDN   | later-version only (backward walking) | listed | MDN            | 11288  | L    | `type == "MDN"`                         |
| MDN   | later-version only (backward walking) | listed | MDN            | 12348  | L    | `type == "MDN"`                         |
| MDN   | later-version only (backward walking) | listed | MDN            | 10763  | R    | `type == "MDN"`                         |
| MDN   | later-version only (backward walking) | listed | MDN            | 11332  | R    | `type == "MDN"`                         |
| DNp01 | later-version only                    | listed | DNp01          | 10010  | L    | `type == "DNp01"`                       |
| DNp01 | later-version only                    | listed | DNp01          | 10001  | R    | `type == "DNp01"`                       |

Side is `somaSide` from the annotation table. It agrees with the `_L` / `_R`
suffix of `instance` for every row above. A later lock that names these
neurons must use `bodyId` or the MaleCNS `type` token (`DNg97` for oDN1).
`data.resolve("oDN1")` has no match.

## Source

BodyIds come from the public MaleCNS v1.0 body-annotation table that
`flymsg fetch` writes, the same file [data](reference/data.md) names:

<https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/body-annotations-male-cns-v1.0-minconf-0.5.feather>

Berg et al., _Cell_ (2026), doi:10.1016/j.cell.2026.08.015. CC-BY 4.0.
`data.build` keeps `status == "Traced"` (165,122 of 211,577 rows). Every
neuron in the table above is `Traced` and `superclass == descending_neuron`.
Read of that file on 2026-10-19, sha256
`2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2`.

`data.resolve` matches an exact `type`, then an exact `instance`, then a
numeric `bodyId`. Queries below use that rule, plus the `synonyms` column
when the named token is absent.

DNp01 is also present, with the same two bodyIds and sides, in the committed
live scenes built from this connectome (`docs/live/looming/scene.json` and
the other looming / DNp01 comparison scenes). That is a repo cross-check, not
a second identity.

No FlyWire root ID is used as a MaleCNS bodyId.

## Required types

### DNa01 — mapped

Query: `status == "Traced"` and `type == "DNa01"`. Two rows, one per side.

| bodyId | instance         | somaSide | flywireType | hemibrainType |
| ------ | ---------------- | -------- | ----------- | ------------- |
| 10442  | DNa01(VES006)\_L | L        | DNa01       | VES006        |
| 10760  | DNa01(VES006)\_R | R        | DNa01       | VES006        |

Two other traced descending neurons have `DNa01` in the instance string:
`DNae001(DNa01)_L` (bodyId 512071) and `DNae001(DNa01)_R` (bodyId 11563).
Their `type` and `flywireType` are `DNae001`. `data.resolve("DNa01")` does
not return them. They are not this type.

### DNa02 — mapped

Query: `status == "Traced"` and `type == "DNa02"`. Two rows, one per side.
No other `type`, `instance`, `synonyms` or `flywireType` value contains
`DNa02`.

| bodyId | instance | somaSide | flywireType |
| ------ | -------- | -------- | ----------- |
| 523769 | DNa02_L  | L        | DNa02       |
| 10360  | DNa02_R  | R        | DNa02       |

### oDN1 — mapped (MaleCNS type `DNg97`)

Query: `status == "Traced"` and `type == "oDN1"`: **zero rows**. The same
filter on `instance == "oDN1"` is also empty. The only annotation that
names oDN1 is `synonyms == "Sapkal 2024: oDN1"` on type `DNg97`.

| bodyId | type  | instance | somaSide | flywireType | synonyms          |
| ------ | ----- | -------- | -------- | ----------- | ----------------- |
| 13805  | DNg97 | DNg97_L  | L        | DNg97       | Sapkal 2024: oDN1 |
| 230783 | DNg97 | DNg97_R  | R        | DNg97       | Sapkal 2024: oDN1 |

Those are the only two `DNg97` neurons. No other traced body carries `oDN1`
in `type`, `instance`, `synonyms` or `flywireType`. The identity is therefore
not missing and not competed. The MaleCNS type token is `DNg97`; oDN1 is the
literature name from Sapkal et al., _Nature_ (2024),
doi:10.1038/s41586-024-07854-7. The Reiser lab MaleCNS cell-type explorer
lists the same alias on the `DNg97` page (`AKA: oDN1 (Sapkal 2024)`); that
page is not the source of the bodyIds.

A later decoder that calls `data.resolve` must pass `DNg97` or the two
bodyIds, not the string `oDN1`.

## Later-version only

The ADR lists MDN and DNp01 for a later decoder version, not this
milestone. They do not decide whether `arena-1` stops. They are inventoried
from the same table so a later version does not have to guess.

### MDN — listed

Query: `status == "Traced"` and `type == "MDN"`. Four neurons, two on each
side, both instances `MDN_L` or `MDN_R`. Synonym on every row:
`Carreira-Rosario 2018: DNp50`. `type == "DNp50"` is empty. Bidaye et al.
2014 (_Science_, doi:10.1126/science.1249964) is the backward-walking
citation the ADR already names; it is not the source of these bodyIds.

| bodyId | instance | somaSide |
| ------ | -------- | -------- |
| 11288  | MDN_L    | L        |
| 12348  | MDN_L    | L        |
| 10763  | MDN_R    | R        |
| 11332  | MDN_R    | R        |

### DNp01 — listed

Query: `status == "Traced"` and `type == "DNp01"`. Two neurons. Synonym:
`Kennedy and Broadie 2018: GF`. The committed looming scenes repeat the same
pair (`docs/live/looming/scene.json`: bodyId 10001 `DNp01(GF)_R`, bodyId
10010 `DNp01(GF)_L`).

| bodyId | instance     | somaSide |
| ------ | ------------ | -------- |
| 10010  | DNp01(GF)\_L | L        |
| 10001  | DNp01(GF)\_R | R        |

## Gains

None. The ADR forbids a default DN gain in code or in docs. Gains, if any,
are declared per run in the experiment lock (`arena-5`) and the run record.
They do not enter this document or `validation/evidence.yaml`.

## Milestone

Required DN identity is mapped. Per the ADR, `arena-1` stops only when a
required type is ambiguous or missing. That did not happen. This commit
still changes only documentation. It does not authorize `arena-2`.

## What is not claimed

- that MaleCNS, DNa01, DNa02 or DNg97 implement steering or walking;
- that the decoder or any gain is biological;
- that `oDN1` is a MaleCNS `type` token (it is not; the token is `DNg97`);
- that MDN or DNp01 enter this milestone's decoder;
- a FlyWire root ID, a guessed bodyId, or a default gain.
