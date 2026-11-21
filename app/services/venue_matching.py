from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VenueMatchRequest:
    reservation_id: int
    starts_at: datetime
    ends_at: datetime
    priority: int
    candidate_venue_ids: tuple[int, ...]


def recommend_venues(requests: Sequence[VenueMatchRequest]) -> dict[int, int]:
    """Return proposed room assignments keyed by reservation ID.

    The batch is small (one requisition), so an exhaustive depth-first search with
    branch-and-bound is deterministic and exact: it maximises the number of placed
    activities first, then applies the priority/application-order/venue tie-breaks.
    """
    # 优先级从高到低、预约编号从小到大，决定比较与选择时使用的活动顺序。
    ordered = sorted(
        (request for request in requests if request.candidate_venue_ids),
        key=lambda request: (-request.priority, request.reservation_id),
    )
    if not ordered:
        return {}

    candidates = [
        tuple(sorted(set(request.candidate_venue_ids))) for request in ordered
    ]
    bookings: dict[int, list[tuple[datetime, datetime]]] = {}
    current: dict[int, int] = {}
    # 先比较完整的活动安置顺序，再比较场地编号。
    best_score: tuple[int, tuple[int, ...], tuple[int, ...]] = (-1, (), ())
    best_assignment: dict[int, int] = {}

    def fits(venue_id: int, starts_at: datetime, ends_at: datetime) -> bool:
        """左闭右开区间：上一场结束等于下一场开始时可以共用场地。"""
        return all(
            not (starts_at < booked_end and booked_start < ends_at)
            for booked_start, booked_end in bookings.get(venue_id, ())
        )

    def additional_upper_bound(index: int) -> int:
        """剩余活动最多还能安置多少：按场地各取最大不重叠集合后求和。

        同一活动可能被多个场地的结果重复计入，因此只会高估，作为剪枝上界是安全的。
        """
        remaining = len(ordered) - index
        venue_ids = {
            venue_id
            for position in range(index, len(ordered))
            for venue_id in candidates[position]
        }
        total = 0
        for venue_id in venue_ids:
            booked = bookings.get(venue_id, ())
            slots = []
            for position in range(index, len(ordered)):
                request = ordered[position]
                if venue_id not in candidates[position]:
                    continue
                if any(
                    request.starts_at < booked_end and booked_start < request.ends_at
                    for booked_start, booked_end in booked
                ):
                    continue
                slots.append((request.ends_at, request.starts_at))
            slots.sort()
            last_end = None
            for end, start in slots:
                if last_end is None or last_end <= start:
                    total += 1
                    last_end = end
            if total >= remaining:
                return remaining
        return total

    def search(index: int, placed: int, scores: list[tuple[int, int]]) -> None:
        nonlocal best_score, best_assignment
        upper_bound = placed + len(ordered) - index
        # 剩余活动全部安置也无法超过当前最优时剪枝。
        if upper_bound < best_score[0]:
            return
        # 用更紧的可安置上界继续剪枝；只有可能持平最优时，才需要比较字典序前缀。
        if best_score[0] >= 0 and upper_bound > best_score[0]:
            upper_bound = placed + additional_upper_bound(index)
            if upper_bound < best_score[0]:
                return
        placements = tuple(placed_here for placed_here, _ in scores)
        if upper_bound == best_score[0] and placements < best_score[1][:index]:
            return
        if index == len(ordered):
            score = (placed, placements, tuple(room_score for _, room_score in scores))
            if score > best_score:
                best_score = score
                best_assignment = dict(current)
            return

        request = ordered[index]

        # 先尝试安置，让搜索尽早得到较好的下界。
        for venue_id in candidates[index]:
            if not fits(venue_id, request.starts_at, request.ends_at):
                continue
            bookings.setdefault(venue_id, []).append((request.starts_at, request.ends_at))
            current[request.reservation_id] = venue_id
            scores.append((1, -venue_id))
            search(index + 1, placed + 1, scores)
            scores.pop()
            del current[request.reservation_id]
            bookings[venue_id].pop()

        # 分支二：本场不参与安置。
        scores.append((0, 0))
        search(index + 1, placed, scores)
        scores.pop()

    search(0, 0, [])
    return best_assignment
