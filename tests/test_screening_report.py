"""Per-cross screening report: contents, saving, sending (docs/screening_report_design.md)."""

import email
import sqlite3
import uuid
from pathlib import Path

import pytest

from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish
from metazebrobot.utils import report_mail

GENOTYPE = "Tg(gfap:PMCA2-mCherry-zf)"
STEP = "20261104T18:23:00"


def _dish(cross, number, allocations=None, screened=20):
    dish = FishDish.create_new(
        cross_id=cross, dish_number=number, genotype=GENOTYPE, responsible="t",
        fish_count=20, dof="20261028", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    if allocations is not None:
        dish["screening_results"] = {"screenings": [{
            "screening_datetime": STEP, "dpf_screened": 7, "indicators_screened": ["mCherry"],
            "count_screened_this_step": screened, "allocations": allocations}]}
    assert data_manager.save_fish_dish(dish)
    return dish["dish_id"]


@pytest.fixture()
def cross():
    cross = f"9{uuid.uuid4().int % 10**8}"
    _dish(cross, 1, [{"bucket": "positive_screened", "disposition": "discarded", "count": 4},
                     {"bucket": "negative_screened", "disposition": "remain_parent", "count": 10}])
    _dish(cross, 2, [{"bucket": "negative_screened", "disposition": "remain_parent", "count": 20}])
    _dish(cross, 3)  # not screened
    return cross


def _no_mail(monkeypatch, tmp_path, **settings):
    monkeypatch.setenv("METAZEBROBOT_MAIL_CONFIG", str(tmp_path / "absent.env"))
    for key in ("MODE", "SMTP_HOST", "MAIL_FROM"):
        monkeypatch.delenv(f"METAZEBROBOT_{key}", raising=False)
    for key, value in settings.items():
        monkeypatch.setenv(f"METAZEBROBOT_{key}", value)


def test_report_counts_flags_and_stamp(client, cross, monkeypatch, tmp_path):
    _no_mail(monkeypatch, tmp_path)
    page = client.get(f"/crosses/{cross}/screening-report").text
    assert f"Cross {cross} screening report" in page
    assert "40 fish screened: <strong>4 positive</strong>," in page
    assert "6 screened without a recorded result" in page
    assert f"Not screened yet: {cross}_3." in page
    assert f"All positives came from {cross}_1" in page
    assert "Generated at " in page and "MetaZebrobot " in page
    assert "Mail mode: <strong>disabled</strong>" in page
    assert client.get("/crosses/NOPE/screening-report").status_code == 404

    download = client.get(f"/crosses/{cross}/screening-report", params={"download": 1})
    assert "attachment" in download.headers["content-disposition"]
    assert "Save report" not in download.text  # the file has no toolbar


def test_save_in_outbox_mode_writes_the_report_and_an_eml(client, cross, monkeypatch, tmp_path):
    _no_mail(monkeypatch, tmp_path, MAIL_MODE="outbox", MAIL_FROM="Lab <lab@example.org>")
    sent = []
    monkeypatch.setattr(report_mail, "send", lambda message, config: sent.append(message))
    page = client.post(f"/crosses/{cross}/screening-report/send",
                       data={"action": "save", "recipients": "a@example.org"}).text
    assert "Report saved with .eml" in page and not sent
    with data_manager.get_connection() as conn:
        row = conn.execute("SELECT * FROM screening_reports WHERE cross_id = ?", (cross,)).fetchone()
    assert Path(row["html_path"]).read_text().startswith("<!doctype html>")
    message = email.message_from_bytes(Path(row["eml_path"]).read_bytes())
    assert message["Subject"] == f"Cross {cross} screening summary" and message["To"] == "a@example.org"
    assert [p.get_filename() for p in message.walk() if p.get_filename()] == [Path(row["html_path"]).name]


def test_send_needs_smtp_mode_and_a_recipient_then_logs_it(client, cross, monkeypatch, tmp_path):
    _no_mail(monkeypatch, tmp_path, MAIL_MODE="outbox")
    assert "Sending is off" in client.post(f"/crosses/{cross}/screening-report/send",
                                           data={"action": "send", "recipients": "a@example.org"}).text
    _no_mail(monkeypatch, tmp_path, MAIL_MODE="smtp", SMTP_HOST="mail.example.org",
             MAIL_FROM="Lab <lab@example.org>")
    sent = []
    monkeypatch.setattr(report_mail, "send", lambda message, config: sent.append((message, config)) or "2.0.0 q1 accepted")
    assert "Enter at least one email address" in client.post(
        f"/crosses/{cross}/screening-report/send", data={"action": "send", "recipients": ""}).text
    page = client.post(f"/crosses/{cross}/screening-report/send",
                       data={"action": "send", "recipients": "a@example.org, b@example.org"}).text
    assert "Report sent" in page and "to a@example.org, b@example.org" in page
    message, config = sent[0]
    assert (config.host, config.port, config.starttls) == ("mail.example.org", 25, False)
    assert message["From"] == "Lab <lab@example.org>"
    with data_manager.get_connection() as conn:
        results = [r[0] for r in conn.execute(
            "SELECT result FROM screening_reports WHERE cross_id = ? ORDER BY id", (cross,))]
    assert results[-1] == "sent (2.0.0 q1 accepted)"


def test_mail_config_reads_a_local_file(tmp_path):
    path = tmp_path / "mail.env"
    path.write_text("# local only\nMETAZEBROBOT_MAIL_MODE=smtp\nMETAZEBROBOT_SMTP_HOST=mail.example.org\n"
                    "METAZEBROBOT_MAIL_FROM='Lab <lab@example.org>'\n")
    config = report_mail.MailConfig.load({"METAZEBROBOT_MAIL_CONFIG": str(path)})
    assert (config.mode, config.host, config.port, config.sender) == (
        "smtp", "mail.example.org", 25, "Lab <lab@example.org>")
    assert config.problem() is None
    assert report_mail.MailConfig.load({"METAZEBROBOT_MAIL_CONFIG": str(tmp_path / "x")}).mode == "disabled"


def test_send_returns_the_servers_queue_reply(monkeypatch):
    calls = []

    class _SMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def ehlo(self):
            return (250, b"ok")

        def mail(self, sender):
            calls.append(("mail", sender))
            return (250, b"ok")

        def rcpt(self, address):
            calls.append(("rcpt", address))
            return (250, b"ok")

        def data(self, body):
            return (250, b"2.0.0 abc123 Message accepted for delivery")

    monkeypatch.setattr(report_mail.smtplib, "SMTP", _SMTP)
    message = report_mail.build_message(sender="Lab <lab@example.org>", recipients=["a@example.org", "b@example.org"],
                                        subject="s", text="t", html="<p>t</p>", attachment_name="r.html",
                                        attachment=b"<html></html>")
    config = report_mail.MailConfig(mode="smtp", host="mail.example.org", sender="Lab <lab@example.org>")
    assert report_mail.send(message, config) == "2.0.0 abc123 Message accepted for delivery"
    assert calls == [("connect", "mail.example.org", 25), ("mail", "lab@example.org"),
                     ("rcpt", "a@example.org"), ("rcpt", "b@example.org")]


def test_plates_count_their_fish_by_current_call(client, monkeypatch, tmp_path):
    _no_mail(monkeypatch, tmp_path)
    cross = f"9{uuid.uuid4().int % 10**8}"
    screened = _dish(cross, 1, allocations=[])
    other = _dish(cross, 2, allocations=[])
    plate = client.post(f"/dishes/{screened}/plate/new", data={"wells": 12},
                        follow_redirects=False).headers["location"].split("/")[2]
    for source, result in ((screened, "positive"), (screened, "positive"), (other, "negative")):
        client.post(f"/dishes/{plate}/plate/add-fish",
                    data={"source_dish_id": source, "result": result, "step": STEP})
    page = client.get(f"/crosses/{cross}/screening-report").text
    row = page.split(f"<td>{plate}")[1].split("</tr>")[0]
    cells = [c.split(">", 1)[1].split("<")[0].strip() for c in row.split("<td")[1:]]
    assert cells[4:8] == ["—", "2", "1", "0"]  # Screened, +, −, pig
    assert f"from {screened} (2), {other} (1); fish calls" in row
    assert "2 fish screened" not in page  # the plate's fish are already in its sources' screens


def test_two_color_cross_reports_each_construct(client, monkeypatch, tmp_path):
    _no_mail(monkeypatch, tmp_path)
    cross = f"9{uuid.uuid4().int % 10**8}"
    two = "Tg(elavl3:H2B-GCaMP7f); Tg(gfap:PMCA2-mCherry-zf)"
    dish = FishDish.create_new(cross_id=cross, dish_number=1, genotype=two, responsible="t",
                               fish_count=10, dof="20261028").model_dump(mode="json", exclude_none=True)
    assert data_manager.save_fish_dish(dish)
    source = dish["dish_id"]
    plate = client.post(f"/dishes/{source}/plate/new", data={"wells": 12},
                        follow_redirects=False).headers["location"].split("/")[2]
    gcamp, mcherry = "Tg(elavl3:H2B-GCaMP7f)", "Tg(gfap:PMCA2-mCherry-zf)"
    for i, results in enumerate(((f"{gcamp}=positive", f"{mcherry}=negative"),
                                 (f"{gcamp}=positive", f"{mcherry}=positive"),
                                 (f"{gcamp}=negative", f"{mcherry}=negative"))):
        client.post(f"/dishes/{plate}/plate/add-fish",  # one new step, then today's step
                    data={"source_dish_id": source, "step": "" if i else "new",
                          "construct_results": list(results)})
    page = client.get(f"/crosses/{cross}/screening-report").text
    assert "H2B-GCaMP7f: <strong>2 positive</strong>, 1 negative" in page
    assert "PMCA2-mCherry-zf: <strong>1 positive</strong>, 2 negative" in page
    plate_row = page.split(f"<td>{plate}")[1].split("</tr>")[0]
    cells = [c.split(">", 1)[1].split("<")[0].strip() for c in plate_row.split("<td")[1:]]
    assert cells[4:9] == ["—", "2", "1", "1", "2"]  # Screened, GCaMP +/−, mCherry +/−
