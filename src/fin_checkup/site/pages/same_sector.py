"""회사 페이지 "같은 업종 회사" — 같은 업종 묶음에서 **이름순으로 이웃한** 회사 몇 곳 + 업종 페이지 링크.

고르는 규칙은 이름순 자리뿐이다. 지표 값·신호·규모로 고르지 않는다 — 값으로 고르면 "이 회사 대신 저 회사"
라는 추천이 된다. 묶음은 업종 페이지(`pages/sector.py`)와 같다 (`site.groups.peer_groups`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from fin_checkup.explain.sectors import peer_group_info
from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.groups import peer_group_of, peer_groups, sector_path
from fin_checkup.site.pages.sector import GroupLink
from fin_checkup.site.registry import company_context

#: 보여 줄 이웃 회사 수 상한.
LIMIT = 12

T = TypeVar("T")


def neighbours(members: Sequence[T], index: int, limit: int = LIMIT) -> list[T]:
    """이름순 목록에서 index 자리 앞뒤로 limit 곳(자기 자신 제외), 이름순 그대로.

    가운데에 두고, 목록 끝에 닿으면 반대쪽으로 더 가져와 limit 를 채운다.
    """
    others = len(members) - 1
    if others <= limit:
        return [m for i, m in enumerate(members) if i != index]
    before = min(index, limit // 2)
    after = min(others - index, limit - before)
    before = limit - after
    return [*members[index - before : index], *members[index + 1 : index + 1 + after]]


@dataclass(frozen=True)
class SameSector:
    group: GroupLink
    #: 이름순.
    peers: list[CompanyEntry]

    @property
    def others(self) -> int:
        """자기 자신을 뺀 같은 업종 회사 수."""
        return self.group.count - 1


@company_context("same_sector")
def same_sector(entry: CompanyEntry, site: Site) -> dict[str, Any]:
    code = peer_group_of(entry)
    members = peer_groups(site).get(code, []) if code else []
    index = next((i for i, m in enumerate(members) if m is entry), None)
    if index is None or len(members) < 2:
        return {"same_sector": None}
    group = GroupLink(peer_group_info(code), sector_path(code), len(members))
    return {"same_sector": SameSector(group, neighbours(members, index))}
