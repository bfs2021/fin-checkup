"""업종 페이지 `/s/<묶음코드>/` · 목록 `/s/`.

묶음은 회사 페이지 대조군과 같은 KSIC 앞 두 자리(`metrics.sector.peer_group_for`). 페이지에는
그 묶음의 쉬운 설명, 지표마다 분포(회사 수·1사분위·중앙값·3사분위 — `site.groups`), 소속 회사 **이름순**.
순위표·"상위 N" 은 만들지 않는다. 지표 값으로 회사를 고르거나 줄 세우지 않는다.

회사 페이지는 `company_context("peer_group")` 가 넘기는 `peer_group` 으로 자기 업종 페이지에 링크한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from fin_checkup.explain.metrics import get_explainer, threshold_text
from fin_checkup.explain.sectors import PeerGroupInfo, peer_group_info
from fin_checkup.metrics.engine import NOT_APPLICABLE_BY_SECTOR
from fin_checkup.metrics.peers import MIN_PEERS
from fin_checkup.metrics.sector import Sector
from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.groups import (
    Distribution,
    distributions,
    peer_group_of,
    peer_groups,
    sector_path,
)
from fin_checkup.site.registry import Output, company_context, page


@dataclass(frozen=True)
class GroupLink:
    info: PeerGroupInfo
    path: str
    count: int


@dataclass(frozen=True)
class Caveat:
    """이 업종에서 ⊘ 로 두는 지표와 대신 볼 것 (`explain.metrics` 의 문장 그대로)."""

    key: str
    label: str
    why: str
    instead: str


@dataclass(frozen=True)
class ThresholdLine:
    #: 묶음 안에 판정 기준이 둘 이상일 때만 붙는다 (지주회사가 섞인 64).
    sector_label: str
    text: str


@dataclass(frozen=True)
class MetricBlock:
    dist: Distribution
    thresholds: tuple[ThresholdLine, ...]
    #: 지표 해설 페이지 경로 (`/m/<key>/`).
    explainer_path: str


def caveats_for(sector: Sector) -> list[Caveat]:
    out: list[Caveat] = []
    for key in NOT_APPLICABLE_BY_SECTOR.get(sector, {}):
        explainer = get_explainer(key)
        caveat = explainer.caveat_for(sector)
        if caveat is not None:
            out.append(Caveat(key, explainer.label, caveat.why, caveat.instead))
    return out


def member_sectors(entries: list[CompanyEntry]) -> list[Sector]:
    """회사들에 실제로 적용된 판정 기준, Sector 정의 순서. 묶음 하나에 둘이 섞일 수 있다(64992)."""
    used = {e.checkup.result.sector for e in entries}
    return [s for s in Sector if s in used]


def metric_blocks(entries: list[CompanyEntry], sectors: list[Sector]) -> list[MetricBlock]:
    """지표마다 분포 + 경계값 문장. 기준이 둘 이상이면 기준마다 한 줄씩 (어느 쪽도 감추지 않는다)."""
    labelled = len(sectors) > 1
    return [
        MetricBlock(
            dist=d,
            thresholds=tuple(
                ThresholdLine(s.label if labelled else "", threshold_text(d.key, s)) for s in sectors
            ),
            explainer_path=f"m/{d.key}/",
        )
        for d in distributions(entries)
    ]


@company_context("peer_group")
def company_peer_group(entry: CompanyEntry, site: Site) -> dict[str, Any]:
    code = peer_group_of(entry)
    if not code:
        return {"peer_group": None}
    members = peer_groups(site).get(code, [])
    return {"peer_group": GroupLink(peer_group_info(code), sector_path(code), len(members))}


@page("sector")
def sector_pages(site: Site) -> Iterator[Output]:
    groups = peer_groups(site)
    links = [GroupLink(peer_group_info(code), sector_path(code), len(m)) for code, m in groups.items()]
    yield site.render(
        "sector/index.html",
        "s/index.html",
        groups=links,
        ungrouped=len(site.companies) - sum(len(m) for m in groups.values()),
        min_peers=MIN_PEERS,
    )
    for link in links:
        members = groups[link.info.code]
        sectors = member_sectors(members)
        yield site.render(
            "sector/group.html",
            link.path + "index.html",
            group=link,
            members=members,
            sectors=sectors,
            blocks=metric_blocks(members, sectors),
            caveats=[c for s in sectors for c in caveats_for(s)],
            min_peers=MIN_PEERS,
        )
