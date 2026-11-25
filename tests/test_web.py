"""The pages show what the logs say at a moment, and a form acts or is refused."""

import re
from datetime import UTC, date, datetime, timedelta
from html import unescape
from http import HTTPStatus
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from jinja2 import UndefinedError

from airworthy import ops, seed
from airworthy.fleet import Aircraft
from airworthy.store import Store
from airworthy.triage import NoSuggestionError
from airworthy.web import ENVIRONMENT, Pages, create_app, main
from airworthy.writeup import (
    Reclassified,
    Reopened,
    Reported,
    Resolved,
    Scheduled,
    Severity,
    Suggestion,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI
    from httpx2 import Response

    from airworthy.writeup import FollowUp

pytestmark = pytest.mark.unit

# The sample fleet's stories end here, and every action in a test is taken here.
NOW: Final = datetime(2026, 3, 3, 7, 30, tzinfo=UTC)
TWO_DAYS_EARLIER: Final = "2026-03-01T07:30"


def _now() -> datetime:
    return NOW


@pytest.fixture
def store(tmp_path: Path) -> Store:
    """Give a store holding the sample fleet, loaded as of `NOW`."""
    made = Store.at(tmp_path / "fleet.db")
    seed.load(made, NOW)
    return made


@pytest.fixture
def client(store: Store) -> TestClient:
    """Give a browser on the app that follows no redirect, with its clock at `NOW`."""
    return TestClient(create_app(store, _now), follow_redirects=False)


def _text(html: str) -> str:
    """Give the words of a piece of a page, as a person reads them."""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _part(page: Response, element: str, end: str) -> str:
    """Give the words inside the element with an id, up to its closing tag."""
    start = page.text.index(f'id="{element}"')
    return _text("<x " + page.text[start : page.text.index(end, start)])


def _row(page: Response, tail: str) -> str:
    return _part(page, tail, "</tr>")


def _problem(page: Response) -> str:
    return _text(page.text[page.text.index('class="problem"') - 3 :].split("</p>")[0])


def _forms(page: Response, write_up_id: int) -> list[str]:
    """Give the kinds of follow-up a write-up's forms offer, in page order."""
    start = page.text.index(f'id="write-up-{write_up_id}"')
    article = page.text[start : page.text.index("</article>", start)]
    found = re.finditer(r'name="kind" value="(\w+)"', article)
    return [match.group(1) for match in found]


def test_the_board_shows_each_aircraft_as_it_stands_now(client: TestClient) -> None:
    page = client.get("/")

    assert page.status_code == HTTPStatus.OK
    assert _part(page, "summary", "</p>") == (
        "Now, 2026-03-03 07:30 UTC: 2 of 6 aircraft cleared to fly."
    )
    assert [_row(page, f"N10{n}AW") for n in range(1, 7)] == [
        "N101AW Airbus A320 Cleared to fly 0 open none none",
        (
            "N102AW Airbus A320 Grounded by #2 Crack in the windshield outer pane, "
            "captain's side 1 open none none"
        ),
        "N103AW Boeing 737-800 Cleared to fly 1 open none #4",
        (
            "N104AW Embraer E175 Grounded by #5 Bird strike damage to the left engine "
            "fan blades; #6 Cabin pressure controller fault on climb 2 open #6 none"
        ),
        (
            "N105AW Embraer E175 Grounded by #7 Nose wheel steering feels stiff during "
            "taxi 1 open none none"
        ),
        (
            "N106AW ATR 72-600 Grounded by #8 Fuel quantity indication unreliable on "
            "the right tank 2 open #8 none"
        ),
    ]


def test_the_board_shows_the_fleet_as_it_stood_at_a_past_moment(
    client: TestClient,
) -> None:
    page = client.get("/", params={"at": TWO_DAYS_EARLIER})

    assert _part(page, "summary", "</p>") == (
        "As it stood at 2026-03-01 07:30 UTC: 4 of 6 aircraft cleared to fly."
    )
    assert [_row(page, f"N10{n}AW") for n in (2, 3, 6)] == [
        "N102AW Airbus A320 Cleared to fly 0 open none none",
        (
            "N103AW Boeing 737-800 Grounded by #3 Hydraulic fluid leaking at the left "
            "main gear actuator 2 open none none"
        ),
        "N106AW ATR 72-600 Cleared to fly 1 open none none",
    ]
    assert 'href="/aircraft/N106AW?at=2026-03-01T07%3A30"' in page.text


def test_a_past_moment_given_with_an_offset_is_that_moment(client: TestClient) -> None:
    page = client.get("/", params={"at": "2026-03-01T16:30:00+09:00"})

    assert _part(page, "summary", "</p>").startswith(
        "As it stood at 2026-03-01 07:30 UTC:"
    )


def test_a_moment_that_is_not_a_time_is_a_bad_request(client: TestClient) -> None:
    page = client.get("/", params={"at": "yesterday"})

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == "yesterday isn't a time such as 2026-01-15T12:00"


def test_an_aircraft_page_tells_each_write_up_and_its_history(
    client: TestClient,
) -> None:
    page = client.get("/aircraft/N106AW")

    assert page.status_code == HTTPStatus.OK
    assert _part(page, "status", "</p>") == "Grounded by #8"
    assert _part(page, "write-up-8", "</ol>") == (
        "#8 Fuel quantity indication unreliable on the right tank "
        "high severity, open, needs a repair date "
        "2026-02-25 08:30 UTC Lin Zhou reported it as high "
        "2026-02-25 09:30 UTC Dee Park set the repair for 2026-02-26 "
        "2026-02-26 11:30 UTC Sam Okafor resolved it: Replaced the fuel probe "
        "2026-03-03 03:30 UTC Ana Reyes reopened it: "
        "Indication dropped out again in cruise"
    )
    assert _part(page, "write-up-9", "</ol>") == (
        "#9 Propeller de-ice boot looks delaminated "
        "medium severity, open, repair set for 2026-03-08 "
        "2026-02-27 05:30 UTC Ana Reyes reported it as high "
        "2026-02-27 08:00 UTC Sam Okafor changed the severity to medium: "
        "Boot is intact; edge lift is cosmetic and within limits "
        "2026-02-27 08:30 UTC Dee Park set the repair for 2026-03-08"
    )
    assert _part(page, "write-up-10", "</p>").endswith(
        "low severity, resolved by Lin Zhou at 2026-03-02 05:00 UTC: "
        "Replaced the handset from stock"
    )


def test_an_overdue_repair_is_told_with_the_date_it_was_set_for(
    client: TestClient,
) -> None:
    page = client.get("/aircraft/N103AW")

    assert _part(page, "status", "</p>") == "Cleared to fly"
    assert _part(page, "write-up-4", "</p>") == (
        "#4 Weather radar display flickers intermittently "
        "medium severity, open, overdue: repair was set for 2026-03-01"
    )


def test_a_write_up_offers_only_the_follow_ups_its_state_allows(
    client: TestClient,
) -> None:
    page = client.get("/aircraft/N106AW")

    assert _forms(page, 8) == ["scheduled", "resolved", "reclassified"]
    assert _forms(page, 10) == ["reopened", "reclassified"]


def test_a_past_view_of_an_aircraft_holds_what_was_known_then_and_no_forms(
    client: TestClient,
) -> None:
    page = client.get("/aircraft/N106AW", params={"at": TWO_DAYS_EARLIER})

    assert "As it stood at 2026-03-01 07:30 UTC." in _text(page.text)
    assert _part(page, "status", "</p>") == "Cleared to fly"
    assert _part(page, "write-up-8", "</ol>").endswith(
        "2026-02-26 11:30 UTC Sam Okafor resolved it: Replaced the fuel probe"
    )
    assert 'id="write-up-10"' not in page.text
    assert "<form" not in page.text


def test_an_unknown_aircraft_is_not_found(client: TestClient) -> None:
    page = client.get("/aircraft/N999ZZ")

    assert page.status_code == HTTPStatus.NOT_FOUND
    assert _problem(page) == "no aircraft N999ZZ"


def test_filing_a_write_up_records_it_now_and_returns_to_the_aircraft(
    client: TestClient, store: Store
) -> None:
    form = {"by": " Ana Reyes ", "severity": "high", "description": "Tyre worn"}

    answer = client.post("/aircraft/N101AW/write-ups", data=form)

    assert answer.status_code == HTTPStatus.SEE_OTHER
    assert answer.headers["location"] == "/aircraft/N101AW"
    assert store.write_ups("N101AW")[-1].reported == Reported(
        at=NOW, by="Ana Reyes", severity=Severity.HIGH, description="Tyre worn"
    )
    assert _row(client.get("/"), "N101AW") == (
        "N101AW Airbus A320 Grounded by #11 Tyre worn 1 open #11 none"
    )


def test_a_write_up_filed_without_a_name_or_a_severity_is_refused(
    client: TestClient, store: Store
) -> None:
    form = {"by": " ", "description": "Tyre worn"}

    page = client.post("/aircraft/N101AW/write-ups", data=form)

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == (
        "by: String should have at least 1 character; severity: Field required"
    )
    assert len(store.write_ups("N101AW")) == 1


def test_filing_on_an_unknown_aircraft_is_not_found(client: TestClient) -> None:
    form = {"by": "Ana Reyes", "severity": "low", "description": "Tyre worn"}

    page = client.post("/aircraft/N999ZZ/write-ups", data=form)

    assert page.status_code == HTTPStatus.NOT_FOUND
    assert _problem(page) == "no aircraft N999ZZ"


@pytest.mark.parametrize(
    ("write_up_id", "tail", "form", "recorded"),
    [
        (
            6,
            "N104AW",
            {"kind": "scheduled", "on": "2026-03-10", "by": "Dee Park"},
            Scheduled(at=NOW, by="Dee Park", on=date(2026, 3, 10)),
        ),
        (
            2,
            "N102AW",
            {"kind": "resolved", "note": "Replaced the pane", "by": "Sam Okafor"},
            Resolved(at=NOW, by="Sam Okafor", note="Replaced the pane"),
        ),
        (
            5,
            "N104AW",
            {
                "kind": "reclassified",
                "severity": "medium",
                "reason": "Blades within limits",
                "by": "Lin Zhou",
            },
            Reclassified(
                at=NOW,
                by="Lin Zhou",
                severity=Severity.MEDIUM,
                reason="Blades within limits",
            ),
        ),
        (
            3,
            "N103AW",
            {"kind": "reopened", "reason": "Leaking again", "by": "Ana Reyes"},
            Reopened(at=NOW, by="Ana Reyes", reason="Leaking again"),
        ),
    ],
)
def test_a_follow_up_is_recorded_now_and_returns_to_the_aircraft(
    client: TestClient,
    store: Store,
    write_up_id: int,
    tail: str,
    form: dict[str, str],
    recorded: FollowUp,
) -> None:
    answer = client.post(f"/write-ups/{write_up_id}/events", data=form)

    assert answer.status_code == HTTPStatus.SEE_OTHER
    assert answer.headers["location"] == f"/aircraft/{tail}"
    assert store.write_up(write_up_id).later[-1] == recorded


def test_resolving_its_only_high_clears_an_aircraft_on_the_board(
    client: TestClient,
) -> None:
    form = {"kind": "resolved", "note": "Replaced the pane", "by": "Sam Okafor"}

    _ = client.post("/write-ups/2/events", data=form)

    assert _row(client.get("/"), "N102AW") == (
        "N102AW Airbus A320 Cleared to fly 0 open none none"
    )


def test_a_follow_up_the_state_refuses_is_told_on_the_aircraft_page(
    client: TestClient, store: Store
) -> None:
    form = {"kind": "resolved", "note": "Replaced the seal", "by": "Sam Okafor"}

    page = client.post("/write-ups/3/events", data=form)

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == "this write-up is already resolved"
    assert _part(page, "status", "</p>") == "Cleared to fly"
    assert _forms(page, 3) == ["reopened", "reclassified"]
    assert len(store.write_up(3).later) == 2


def test_a_follow_up_with_blank_fields_is_refused_and_names_them(
    client: TestClient, store: Store
) -> None:
    form = {"kind": "resolved", "note": "", "by": " "}

    page = client.post("/write-ups/2/events", data=form)

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == (
        "by: String should have at least 1 character;"
        " note: String should have at least 1 character"
    )
    assert len(store.write_up(2).later) == 1


def test_a_repair_date_that_is_not_a_date_is_refused(client: TestClient) -> None:
    form = {"kind": "scheduled", "on": "someday", "by": "Dee Park"}

    page = client.post("/write-ups/6/events", data=form)

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page).startswith("on: Input should be a valid date")


def test_a_follow_up_on_an_unknown_write_up_is_not_found(client: TestClient) -> None:
    form = {"kind": "resolved", "note": "Replaced the pane", "by": "Sam Okafor"}

    page = client.post("/write-ups/99/events", data=form)

    assert page.status_code == HTTPStatus.NOT_FOUND
    assert _problem(page) == "no write-up 99"


@pytest.fixture
def served() -> list[tuple[FastAPI, int]]:
    """Give the list a stand-in server records each app and port it is given in."""
    return []


def test_main_serves_the_sample_fleet_on_port_8000(
    served: list[tuple[FastAPI, int]],
) -> None:
    def serve(app: FastAPI, *, port: int) -> None:
        served.append((app, port))

    main([], serve)

    [(app, port)] = served
    assert port == 8000
    summary = _part(TestClient(app).get("/"), "summary", "</p>")
    assert summary.endswith("2 of 6 aircraft cleared to fly.")


def test_main_takes_a_port_and_keeps_the_fleet_in_a_named_file(
    served: list[tuple[FastAPI, int]], tmp_path: Path
) -> None:
    database = tmp_path / "kept" / "here" / "fleet.db"

    def serve(app: FastAPI, *, port: int) -> None:
        served.append((app, port))

    main(["--port", "9000", "--db", str(database)], serve)

    assert [port for _, port in served] == [9000]
    assert len(Store.at(database).all_aircraft()) == 6


def test_main_leaves_a_database_that_has_a_fleet_as_it_is(
    served: list[tuple[FastAPI, int]], tmp_path: Path
) -> None:
    database = tmp_path / "fleet.db"
    cub = Aircraft(tail="N1", type="Piper Cub")
    Store.at(database).add_aircraft(cub)

    def serve(app: FastAPI, *, port: int) -> None:
        served.append((app, port))

    main(["--db", str(database)], serve)

    assert Store.at(database).all_aircraft() == [cub]
    assert len(served) == 1


def test_what_a_person_typed_is_shown_as_text_and_never_as_markup(
    client: TestClient,
) -> None:
    form = {"by": "Ana Reyes", "severity": "high", "description": "<b>Tyre</b> worn"}

    _ = client.post("/aircraft/N101AW/write-ups", data=form)

    for page in (client.get("/"), client.get("/aircraft/N101AW")):
        assert "&lt;b&gt;Tyre&lt;/b&gt; worn" in page.text
        assert "<b>Tyre</b>" not in page.text


@pytest.mark.parametrize("at", ["9999-12-31T23:00-05:00", "0001-01-01T00:00+05:00"])
@pytest.mark.parametrize("path", ["/", "/aircraft/N102AW"])
def test_a_moment_outside_the_years_a_page_can_tell_is_a_bad_request(
    client: TestClient, path: str, at: str
) -> None:
    page = client.get(path, params={"at": at})

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == f"{at} isn't a time such as 2026-01-15T12:00"


def test_a_write_up_id_too_large_for_the_database_is_not_found(
    client: TestClient,
) -> None:
    form = {"kind": "resolved", "by": "Sam Okafor", "note": "Replaced the tyre"}

    page = client.post(f"/write-ups/{2**63}/events", data=form)

    assert page.status_code == HTTPStatus.NOT_FOUND
    assert _problem(page) == "no write-up 9223372036854775808"


def test_a_field_no_event_has_is_refused_on_the_aircraft_page(
    client: TestClient, store: Store
) -> None:
    form = {"kind": "resolved", "by": "Sam", "note": "Replaced it", "extra": "1"}

    page = client.post("/write-ups/2/events", data=form)

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == "extra: Extra inputs are not permitted"
    assert len(store.write_up(2).later) == 1


def test_a_time_a_form_posts_is_ignored_for_the_clocks(
    client: TestClient, store: Store
) -> None:
    """Nobody chooses when their action happened: the server's clock says."""
    form = {"by": "Ana", "severity": "low", "description": "Tyre worn"}

    _ = client.post("/aircraft/N101AW/write-ups", data={**form, "at": "2020-01-01Z"})
    _ = client.post(
        "/write-ups/11/events",
        data={"kind": "resolved", "by": "Sam", "note": "Done", "at": "2020-01-01Z"},
    )

    filed = store.write_up(11)
    assert [filed.reported.at, *(event.at for event in filed.later)] == [NOW, NOW]


def test_a_past_view_keeps_the_moment_asked_for_and_links_back_to_now(
    client: TestClient,
) -> None:
    board = client.get("/", params={"at": TWO_DAYS_EARLIER})
    aircraft = client.get("/aircraft/N102AW", params={"at": TWO_DAYS_EARLIER})

    assert f'name="at" value="{TWO_DAYS_EARLIER}"' in board.text
    assert '<a href="/">Back to now</a>' in board.text
    assert '<a href="/aircraft/N102AW">Back to now</a>' in aircraft.text
    assert "Back to now" not in client.get("/").text
    assert "Back to now" not in client.get("/aircraft/N102AW").text


def test_an_aircraft_with_no_write_ups_says_so(
    client: TestClient, store: Store
) -> None:
    store.add_aircraft(Aircraft(tail="N1", type="Piper Cub"))

    now = client.get("/aircraft/N1")
    earlier = client.get("/aircraft/N102AW", params={"at": "2020-01-01"})

    assert "<p>No write-ups.</p>" in now.text
    assert "<p>No write-ups by then.</p>" in earlier.text


def test_an_aircraft_grounded_twice_names_both_write_ups(client: TestClient) -> None:
    form = {"by": "Ana Reyes", "severity": "high", "description": "Tyre worn"}

    _ = client.post("/aircraft/N101AW/write-ups", data=form)
    _ = client.post("/aircraft/N101AW/write-ups", data=form)

    page = client.get("/aircraft/N101AW")
    assert _part(page, "status", "</p>") == "Grounded by #11, #12"


def test_a_page_says_it_is_utf_8(client: TestClient) -> None:
    assert '<meta charset="utf-8">' in client.get("/").text


def test_a_template_that_names_something_it_was_not_given_fails() -> None:
    """A misspelled name in a page must not render as nothing."""
    with pytest.raises(UndefinedError, match="'misspelled' is undefined"):
        _ = ENVIRONMENT.from_string("{{ misspelled }}").render()


def test_only_a_write_up_waiting_or_overdue_is_marked_for_attention(
    client: TestClient,
) -> None:
    """On N106AW, #8 waits for a repair date, #9 has one and #10 is resolved."""
    page = client.get("/aircraft/N106AW").text
    overdue = client.get("/aircraft/N103AW").text
    waiting = page[page.index('id="write-up-8"') :]
    resolved = page[page.index('id="write-up-10"') :]

    assert '<p class="standing overdue">high severity, open, needs' in waiting
    assert '<p class="standing">' in resolved.split("</p>")[0]
    assert '<p class="standing">medium severity, open, repair set for' in page
    assert '<p class="standing overdue">medium severity, open, overdue' in overdue


def _suggest(description: str) -> Suggestion:
    return Suggestion(severity=Severity.HIGH, reason=f"<i>About</i>: {description}")


def _no_suggestion(description: str) -> Suggestion:
    msg = f"nothing to say about {description}"
    raise NoSuggestionError(msg)


@pytest.fixture
def triaged(store: Store) -> TestClient:
    """Give a browser on an app whose suggester always suggests high."""
    return TestClient(create_app(store, _now, _suggest), follow_redirects=False)


def _carried(page: Response) -> str:
    """Give what the filing form's hidden field carries back, as a browser posts it."""
    found = re.search(r'name="suggested" value="([^"]*)"', page.text)
    assert found is not None
    return unescape(found.group(1))


def test_asking_for_a_suggestion_shows_it_and_files_nothing(
    triaged: TestClient, store: Store
) -> None:
    form = {"description": " Fluid under the left gear ", "by": "Ana Reyes"}

    page = triaged.post("/aircraft/N101AW/suggestion", data=form)

    assert page.status_code == HTTPStatus.OK
    assert _part(page, "suggestion", "</p>") == (
        "Suggested severity: high . A model generated this from the description;"
        " the choice below is yours."
    )
    assert "<summary>Why</summary>&lt;i&gt;About&lt;/i&gt;: Fluid under" in page.text
    assert ">Fluid under the left gear</textarea>" in page.text
    assert "checked" not in page.text
    assert len(store.write_ups("N101AW")) == 1


def test_a_suggestion_is_recorded_beside_the_severity_the_person_picked(
    triaged: TestClient, store: Store
) -> None:
    asked = {"description": "Fluid under the left gear"}
    suggested = _carried(triaged.post("/aircraft/N101AW/suggestion", data=asked))
    form = {**asked, "by": "Ana Reyes", "severity": "medium", "suggested": suggested}

    answer = triaged.post("/aircraft/N101AW/write-ups", data=form)

    assert answer.status_code == HTTPStatus.SEE_OTHER
    assert store.write_ups("N101AW")[-1].reported == Reported(
        at=NOW,
        by="Ana Reyes",
        severity=Severity.MEDIUM,
        description="Fluid under the left gear",
        suggested=_suggest("Fluid under the left gear"),
    )
    assert _part(triaged.get("/aircraft/N101AW"), "write-up-11", "</li>").endswith(
        "Ana Reyes reported it as medium (a model suggested high: <i>About</i>:"
        " Fluid under the left gear) Filed below the suggested severity."
    )


def test_a_report_filed_at_the_suggested_severity_carries_no_warning(
    triaged: TestClient,
) -> None:
    asked = {"description": "Tyre worn"}
    suggested = _carried(triaged.post("/aircraft/N101AW/suggestion", data=asked))
    form = {"by": "Ana", "severity": "high", "description": "Tyre worn"}

    _ = triaged.post(
        "/aircraft/N101AW/write-ups", data={**form, "suggested": suggested}
    )

    assert _part(triaged.get("/aircraft/N101AW"), "write-up-11", "</li>").endswith(
        "Ana reported it as high (a model suggested high: <i>About</i>: Tyre worn)"
    )


def test_a_report_filed_without_asking_tells_of_no_suggestion(
    triaged: TestClient,
) -> None:
    form = {"by": "Ana", "severity": "low", "description": "Tyre worn"}

    _ = triaged.post("/aircraft/N101AW/write-ups", data=form)

    history = _part(triaged.get("/aircraft/N101AW"), "write-up-11", "</li>")
    assert history.endswith("Ana reported it as low")


@pytest.mark.parametrize(
    ("carried", "problem"),
    [
        ("{high", "suggested: Invalid JSON: key must be a string at line 1 column 2"),
        (
            '{"suggestion": {"severity": "extreme", "reason": "Fluid"}, "seal": "0"}',
            "severity: Input should be 'high', 'medium' or 'low'",
        ),
    ],
)
def test_a_carried_suggestion_that_is_not_one_is_refused(
    triaged: TestClient, store: Store, carried: str, problem: str
) -> None:
    form = {"by": "Ana", "severity": "low", "description": "Tyre worn"}

    page = triaged.post(
        "/aircraft/N101AW/write-ups", data={**form, "suggested": carried}
    )

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == problem
    assert len(store.write_ups("N101AW")) == 1


def test_a_suggestion_is_not_recorded_for_a_description_it_was_not_made_for(
    triaged: TestClient, store: Store
) -> None:
    """The person asked about one description, then filed another."""
    asked = {"description": "Coffee stain on a seat"}
    suggested = _carried(triaged.post("/aircraft/N101AW/suggestion", data=asked))
    form = {"description": "Engine fire warning light on", "suggested": suggested}

    page = triaged.post(
        "/aircraft/N101AW/write-ups", data={**form, "by": "Ana", "severity": "low"}
    )

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == (
        "that suggestion was not made for this description; ask for another, or file"
        " without one"
    )
    assert ">Engine fire warning light on</textarea>" in page.text
    assert 'name="suggested"' not in page.text
    assert len(store.write_ups("N101AW")) == 1


def test_a_suggestion_this_app_did_not_seal_is_refused(
    client: TestClient, triaged: TestClient, store: Store
) -> None:
    """Another app sealed it, with a key of its own: here it is as good as made up."""
    asked = {"description": "Tyre worn"}
    suggested = _carried(triaged.post("/aircraft/N101AW/suggestion", data=asked))
    form = {**asked, "by": "Ana", "severity": "low", "suggested": suggested}

    page = client.post("/aircraft/N101AW/write-ups", data=form)

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page).startswith("that suggestion was not made for this")
    assert len(store.write_ups("N101AW")) == 1


@pytest.mark.parametrize("form", [{}, {"description": "   "}])
def test_a_suggestion_needs_a_description(
    triaged: TestClient, form: dict[str, str]
) -> None:
    page = triaged.post("/aircraft/N101AW/suggestion", data=form)

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == "description: String should have at least 1 character"
    assert 'id="suggestion"' not in page.text


def test_a_suggestion_the_model_did_not_give_keeps_what_was_typed(
    store: Store,
) -> None:
    app = create_app(store, _now, _no_suggestion)

    page = TestClient(app).post(
        "/aircraft/N101AW/suggestion", data={"description": "Tyre worn"}
    )

    assert page.status_code == HTTPStatus.BAD_GATEWAY
    assert _problem(page) == "nothing to say about Tyre worn"
    assert ">Tyre worn</textarea>" in page.text
    assert 'id="suggestion"' not in page.text


def test_a_suggestion_for_an_unknown_aircraft_is_not_found_and_asks_no_model(
    store: Store,
) -> None:
    asked: list[str] = []

    def suggest(description: str) -> Suggestion:
        asked.append(description)
        return _suggest(description)

    browser = TestClient(create_app(store, _now, suggest))

    page = browser.post("/aircraft/N999ZZ/suggestion", data={"description": "Tyre"})

    assert page.status_code == HTTPStatus.NOT_FOUND
    assert _problem(page) == "no aircraft N999ZZ"
    assert asked == []


def test_a_page_asked_for_without_a_moment_is_shown_as_of_now(store: Store) -> None:
    """Called as a function, as the app calls it once a request has no `at`."""
    pages = Pages(store=store, clock=_now, suggester=None, asker=None, key=b"a key")

    assert pages.board().status_code == HTTPStatus.OK
    assert pages.aircraft("N101AW").status_code == HTTPStatus.OK


def test_an_app_with_no_suggester_neither_offers_nor_serves_a_suggestion(
    client: TestClient, triaged: TestClient
) -> None:
    offer = '<button formaction="/aircraft/N101AW/suggestion" formnovalidate>'
    asked = {"description": "Tyre worn"}

    assert offer in triaged.get("/aircraft/N101AW").text
    assert "formaction" not in client.get("/aircraft/N101AW").text
    assert (
        client.post("/aircraft/N101AW/suggestion", data=asked).status_code
        == HTTPStatus.NOT_FOUND
    )


def test_the_sample_fleet_tells_of_a_report_filed_below_its_suggestion(
    client: TestClient,
) -> None:
    history = _part(client.get("/aircraft/N105AW"), "write-up-7", "</li>")

    assert "reported it as medium (a model suggested high: Stiff nose" in history
    assert history.endswith("Filed below the suggested severity.")


@pytest.mark.parametrize(
    ("environ", "offered"),
    [
        ({"ANTHROPIC_API_KEY": "a-key"}, True),
        ({"ANTHROPIC_API_KEY": ""}, False),
        ({}, False),
    ],
)
def test_main_offers_what_a_model_does_only_with_a_key_for_it(
    served: list[tuple[FastAPI, int]], environ: dict[str, str], *, offered: bool
) -> None:
    def serve(app: FastAPI, *, port: int) -> None:
        served.append((app, port))

    main([], serve, environ)

    [(app, _)] = served
    browser = TestClient(app)
    assert ("Suggest a severity" in browser.get("/aircraft/N101AW").text) is offered
    assert ("Ask about the fleet" in browser.get("/").text) is offered


def test_the_board_marks_the_overdue_column_only_where_a_repair_is_overdue(
    client: TestClient,
) -> None:
    """N103AW's #4 is past its repair date; N101AW has nothing open."""
    board = client.get("/").text
    late = board[board.index('<tr id="N103AW"') :].split("</tr>")[0]
    quiet = board[board.index('<tr id="N101AW"') :].split("</tr>")[0]

    assert '<td class="overdue">#4 </td>' in late
    assert '<td class="">none</td>' in quiet


def _statuses(fleet: tuple[ops.Listed, ...]) -> str:
    return ", ".join(
        f"{listed.aircraft.tail} {type(listed.status).__name__}" for listed in fleet
    )


def _answer(question: str, reads: ops.Reads) -> str:
    """Answer with the question and what each read gives, as a model's tools see it."""
    filed = reads.write_ups("N103AW") or ()
    stands = ", ".join(
        f"#{one.write_up.id} {type(one.state).__name__}" for one in filed
    )
    return (
        f"<q>{question}</q> at {reads.now():%Y-%m-%d %H:%M}."
        f" Now: {_statuses(reads.fleet(None))}."
        f" Before: {_statuses(reads.fleet(NOW - timedelta(days=2)))}."
        f" N103AW: {stands}. N999ZZ: {reads.write_ups('N999ZZ')}."
    )


def _no_answer(question: str, _reads: ops.Reads) -> str:
    msg = f"nothing to say about {question}"
    raise ops.NoAnswerError(msg)


@pytest.fixture
def asking(store: Store) -> TestClient:
    """Give a browser on an app whose question box answers with `_answer`."""
    return TestClient(create_app(store, _now, asker=_answer))


def test_a_question_is_answered_from_this_store_by_this_clock(
    asking: TestClient,
) -> None:
    """The answer shows what the reads gave, so reads wired elsewhere would show."""
    page = asking.post("/questions", data={"question": "Which can fly?"})

    assert page.status_code == HTTPStatus.OK
    assert _part(page, "answer", "</p>") == (
        "<q>Which can fly?</q> at 2026-03-03 07:30."
        " Now: N101AW Cleared, N102AW Grounded, N103AW Cleared, N104AW Grounded,"
        " N105AW Grounded, N106AW Grounded."
        " Before: N101AW Cleared, N102AW Cleared, N103AW Grounded, N104AW Grounded,"
        " N105AW Cleared, N106AW Cleared."
        " N103AW: #3 Closed, #4 Open. N999ZZ: None."
        " A model wrote this answer from the records. The board below is the record."
    )
    assert "&lt;q&gt;Which can fly?&lt;/q&gt;" in page.text
    assert 'name="question" size="60" value="Which can fly?"' in page.text
    assert _part(page, "summary", "</p>").endswith("2 of 6 aircraft cleared to fly.")


@pytest.mark.parametrize("posted", [{"question": "  "}, {}])
def test_a_blank_or_missing_question_is_refused(
    asking: TestClient, posted: dict[str, str]
) -> None:
    page = asking.post("/questions", data=posted)

    assert page.status_code == HTTPStatus.BAD_REQUEST
    assert _problem(page) == "question: String should have at least 1 character"
    assert 'id="answer"' not in page.text
    assert 'name="question" size="60" value=""' in page.text


def test_a_question_the_model_did_not_answer_keeps_what_was_asked(
    store: Store,
) -> None:
    app = create_app(store, _now, asker=_no_answer)

    page = TestClient(app).post("/questions", data={"question": "Which can fly?"})

    assert page.status_code == HTTPStatus.BAD_GATEWAY
    assert _problem(page) == "nothing to say about Which can fly?"
    assert 'name="question" size="60" value="Which can fly?"' in page.text
    assert 'id="answer"' not in page.text


def test_an_app_with_no_asker_neither_offers_nor_serves_a_question(
    client: TestClient, asking: TestClient
) -> None:
    box = '<form method="post" action="/questions">'
    asked = {"question": "Which can fly?"}

    assert box in asking.get("/").text
    assert 'class="problem"' not in asking.get("/").text
    assert box not in client.get("/").text
    assert client.post("/questions", data=asked).status_code == HTTPStatus.NOT_FOUND


def test_a_past_view_of_the_board_has_no_question_box(asking: TestClient) -> None:
    past = asking.get("/", params={"at": TWO_DAYS_EARLIER})

    assert 'action="/questions"' not in past.text
