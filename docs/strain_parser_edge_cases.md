# Strain Name Parser: Known Edge Cases

The `strain_parser.parse_strain_name()` utility extracts transgenic indicator components from PyRAT strain name strings. It handles the common `Tg(promoter:reporter)` notation well, but some strain names in PyRAT use inconsistent or complex notation that the parser cannot fully decompose. These cases are flagged for user review.

## What Parses Cleanly

Standard notation with one or more semicolon-separated constructs:

| Strain Name | Result |
|---|---|
| `Tg(gfap:TRPV1-T2A-GFP); Tg(elavl3:jRGECO1b)` | tg, gfap, TRPV1-T2A-GFP + tg, elavl3, jRGECO1b |
| `Et(1121A:GAL4FF)` | other, 1121A, GAL4FF |
| `TgBAC(gng8:nfsB-2a-GFP-CAAX)c375` | tg, gng8, nfsB-2a-GFP-CAAX |
| `Casper_HHMI` | (no constructs — correctly ignored) |

## Known Edge Cases

### Semicolons inside parentheses

Some construct names contain semicolons within the parenthesized content, which means multiple elements get lumped into a single reporter string:

```
Tg(gfap:Cas9-t2a-GFP; u6:adra1bbgRNA1;u6:adra1bbgRNA2)
  -> [tg] gfap : Cas9-t2a-GFP; u6:adra1bbgRNA1;u6:adra1bbgRNA2

Tg(il1b:mRuby3;cmlc2:TagBFP2)
  -> [tg] il1b : mRuby3;cmlc2:TagBFP2
```

These are multi-element constructs where the semicolons separate components within a single insertion. The parser treats the whole content after the first colon as the reporter. The user will see the full string during review and can correct if needed.

### Double colons and brackets in promoter names

```
Tg(T2[bactin2::H2B-HaloTag]; myl7:GFP)
  -> [tg] T2[bactin2 : :H2B-HaloTag]; myl7:GFP
```

The `::` and bracket notation causes the first-colon split to land in the wrong place. This is a rare notation and will need manual correction during review.

### Bare UAS constructs (no Tg/Et prefix)

```
(UAS:jRGECO1b)
  -> [?] UAS : jRGECO1b

(5XUAS:TEMPO)
  -> [?] 5XUAS : TEMPO
```

These parse correctly into promoter and reporter, but `modification_type` is `None` because there's no prefix. The `?` flags these for the user to classify.

### Multi-construct strings with mixed separators

```
Tg(elavl3:Gal4-VP16; Rh1:DsRed-Express), (UAS:H2B-jRGECO1a)
  -> [tg] elavl3 : Gal4-VP16; Rh1:DsRed-Express
  -> [?] UAS : H2B-jRGECO1a
```

The first construct contains an internal semicolon that gets absorbed into the reporter, same as the first edge case above. The second construct parses fine.

## Fields That Always Require User Input

Regardless of how well the parser works, two fields cannot be derived from the strain name:

- **`color`** — the fluorescent color (e.g., Green, Red) is not encoded in the notation
- **`expected_expression`** — the expression pattern (e.g., pan-glial, pan-neuronal) requires biological knowledge

These are always left as `None` by the parser and must be filled in during review.
