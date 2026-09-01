# Current capability display-name diagnostic — 2026-08-31

> `LOCAL_CAPABILITY_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`
>
> This is a read-only diagnostic of the current HiThink SH/SZ universe and exact
> AkShare Sina sector source. It is not the 2026-08-31 formal attempt, does not
> backfill that attempt, and does not create a READY manifest, package, frozen
> artifact, watchlist, or returns evidence.

## Registered comparison rule

The comparison used one fixed rule:

1. remove only the explicit zero-width formatting code points `U+200B`, `U+200C`,
   `U+200D`, `U+2060`, and `U+FEFF`;
2. apply Unicode NFKC;
3. trim leading/trailing whitespace.

The rule is versioned as
`DISPLAY_NAME_NORMALIZATION_NFKC_TRIM_EXPLICIT_ZERO_WIDTH_V1`. It does not remove
interior whitespace, `ST`/`*ST`, A/B markers, listing-status suffixes, or other
name characters. All values below are the provider raw values; the normalized
comparison is shown as a diagnosis, not as permission to use fuzzy matching.

## 000012 first-read raw values

| source | raw display name | raw code points | normalized value | normalized code points |
| --- | --- | --- | --- | --- |
| HiThink universe | `南玻Ａ` | `U+5357 U+73BB U+FF21` | `南玻A` | `U+5357 U+73BB U+0041` |
| AkShare Sina member | `南 玻Ａ` | `U+5357 U+0020 U+73BB U+FF21` | `南 玻A` | `U+5357 U+0020 U+73BB U+0041` |

The normalized values are unequal because the sector value contains an interior
`U+0020`. This is not removed by the registered rule.

## Complete current-snapshot counts

| measure | result |
| --- | ---: |
| HiThink raw universe rows | 5,563 |
| `SH_SZ_A_SHARE_ONLY` universe symbols | 5,220 |
| exact Sina sector definitions | 49 |
| completed sector-member calls | 49 |
| sector member raw rows | 2,983 |
| sector member unique symbols | 2,978 |
| total common symbols | 2,539 |
| exact raw-name matches among common symbols | 2,492 |
| raw-name mismatches | 47 |
| normalized-name mismatches among those 47 | 47 |
| representation-only mismatches resolved by the rule | 0 |

The 2,681 universe symbols outside the sector result and the 439 sector symbols
outside the universe are separate coverage signals. They are not silently removed
or substituted. Three common symbols also had repeated sector rows with the same
name; these are structural duplicate-membership signals, not name mismatches, and
remain fail-closed under the existing contract:

| symbol | repeated raw sector name |
| --- | --- |
| `002217` | `ST合力泰` |
| `002617` | `露笑科技` |
| `600714` | `金瑞矿业` |

## Every raw-name mismatch

For every row in the first table, normalized equality is `false`. The sector raw
value inserts one or more interior `U+0020` characters; where `Ａ` is present,
NFKC changes it to ASCII `A` on both sides but does not remove the interior space.

| symbol | universe raw name | sector raw name | code-point / normalized diagnosis |
| --- | --- | --- | --- |
| `000002` | `万科Ａ` | `万 科Ａ` | sector adds interior `U+0020`; normalized unequal |
| `000012` | `南玻Ａ` | `南 玻Ａ` | sector adds interior `U+0020`; normalized unequal |
| `000025` | `特力Ａ` | `特 力Ａ` | sector adds interior `U+0020`; normalized unequal |
| `000058` | `深赛格` | `深 赛 格` | sector adds interior `U+0020`; normalized unequal |
| `000061` | `农产品` | `农 产 品` | sector adds interior `U+0020`; normalized unequal |
| `000088` | `盐田港` | `盐 田 港` | sector adds interior `U+0020`; normalized unequal |
| `000402` | `金融街` | `金 融 街` | sector adds interior `U+0020`; normalized unequal |
| `000514` | `渝开发` | `渝 开 发` | sector adds interior `U+0020`; normalized unequal |
| `000528` | `柳工` | `柳 工` | sector adds interior `U+0020`; normalized unequal |
| `000635` | `英力特` | `英 力 特` | sector adds interior `U+0020`; normalized unequal |
| `000726` | `鲁泰Ａ` | `鲁 泰Ａ` | sector adds interior `U+0020`; normalized unequal |
| `000735` | `罗牛山` | `罗 牛 山` | sector adds interior `U+0020`; normalized unequal |
| `000858` | `五粮液` | `五 粮 液` | sector adds interior `U+0020`; normalized unequal |
| `000869` | `张裕Ａ` | `张 裕Ａ` | sector adds interior `U+0020`; normalized unequal |
| `000876` | `新希望` | `新 希 望` | sector adds interior `U+0020`; normalized unequal |
| `000931` | `中关村` | `中 关 村` | sector adds interior `U+0020`; normalized unequal |
| `000997` | `新大陆` | `新 大 陆` | sector adds interior `U+0020`; normalized unequal |
| `002001` | `新和成` | `新 和 成` | sector adds interior `U+0020`; normalized unequal |
| `002029` | `七匹狼` | `七 匹 狼` | sector adds interior `U+0020`; normalized unequal |
| `002032` | `苏泊尔` | `苏 泊 尔` | sector adds interior `U+0020`; normalized unequal |
| `002040` | `南京港` | `南 京 港` | sector adds interior `U+0020`; normalized unequal |
| `002043` | `兔宝宝` | `兔 宝 宝` | sector adds interior `U+0020`; normalized unequal |
| `002081` | `金螳螂` | `金 螳 螂` | sector adds interior `U+0020`; normalized unequal |
| `002095` | `生意宝` | `生 意 宝` | sector adds interior `U+0020`; normalized unequal |
| `002136` | `安纳达` | `安 纳 达` | sector adds interior `U+0020`; normalized unequal |
| `002154` | `报喜鸟` | `报 喜 鸟` | sector adds interior `U+0020`; normalized unequal |
| `002161` | `远望谷` | `远 望 谷` | sector adds interior `U+0020`; normalized unequal |
| `002165` | `红宝丽` | `红 宝 丽` | sector adds interior `U+0020`; normalized unequal |
| `002181` | `粤传媒` | `粤 传 媒` | sector adds interior `U+0020`; normalized unequal |
| `002183` | `怡亚通` | `怡 亚 通` | sector adds interior `U+0020`; normalized unequal |
| `002186` | `全聚德` | `全 聚 德` | sector adds interior `U+0020`; normalized unequal |
| `002206` | `海利得` | `海 利 得` | sector adds interior `U+0020`; normalized unequal |
| `002209` | `达意隆` | `达 意 隆` | sector adds interior `U+0020`; normalized unequal |
| `002215` | `诺普信` | `诺 普 信` | sector adds interior `U+0020`; normalized unequal |
| `002224` | `三力士` | `三 力 士` | sector adds interior `U+0020`; normalized unequal |
| `002264` | `新华都` | `新 华 都` | sector adds interior `U+0020`; normalized unequal |

The remaining mismatches have listing-status suffixes in the HiThink raw name.
The sector value omits the listed ASCII code points; removing them would be a
semantic guess and is therefore prohibited.

| symbol | universe raw name | sector raw name | code-point / normalized diagnosis |
| --- | --- | --- | --- |
| `301666` | `大普微-UW` | `大普微` | sector omits `U+002D U+0055 U+0057`; normalized unequal |
| `688759` | `必贝特-U` | `必贝特` | sector omits `U+002D U+0055`; normalized unequal |
| `688765` | `禾元生物-U` | `禾元生物` | sector omits `U+002D U+0055`; normalized unequal |
| `688781` | `视涯科技-UW` | `视涯科技` | sector omits `U+002D U+0055 U+0057`; normalized unequal |
| `688783` | `西安奕材-U` | `西安奕材` | sector omits `U+002D U+0055`; normalized unequal |
| `688790` | `昂瑞微-U` | `昂瑞微` | sector omits `U+002D U+0055`; normalized unequal |
| `688795` | `摩尔线程-U` | `摩尔线程` | sector omits `U+002D U+0055`; normalized unequal |
| `688802` | `沐曦股份-U` | `沐曦股份` | sector omits `U+002D U+0055`; normalized unequal |
| `688806` | `泰诺麦博-U` | `泰诺麦博` | sector omits `U+002D U+0055`; normalized unequal |
| `688828` | `国仪量子-U` | `国仪量子` | sector omits `U+002D U+0055`; normalized unequal |
| `688836` | `宇树科技-W` | `宇树科技` | sector omits `U+002D U+0057`; normalized unequal |

## Decision

No current mismatch is resolved by the registered normalization. The live adapter
must therefore keep the name check fail-closed and classify this blocker as
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SUBSTANTIVE_NAME_CONFLICT`. This diagnostic
does not reopen, rerun, or rewrite the 2026-08-31 formal attempt.
