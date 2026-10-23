"""`make e2e`: the plugin on the plugin harness of the runtime it pins
(contract v20), beside `reader`, a reporting plugin (e2e/reader.py) entitled
to its dataset, and the harness's admin. Run from the repository's root by
the Makefile, which builds the image and writes the harness's plugins first;
standard library only.

1. The Board unreachable: the plugin's hosts file sends the Board's site
   nowhere, so its first check fails, and Connection says so -- "Not
   answering", the data role's word -- and records nothing.
2. Sample data on (a developer's setting, accepted on the harness): the
   plugin reads the committed release of 5 October 2026, resolves the
   dollar and the 23 currencies to cash instruments, and records 115 rates;
   Datasets lists each currency with its instrument. It reads H.15's and the
   zero curve's committed files too (Connection's Sources tab), and, the
   harness's master holding none of the referential records the platform
   seeds (only two by test FIGIs), reports each record missing and records
   no rate: what a deployment without them sees (Datasets' Records tab).
3. Parity: through the deployment's MCP, `read_connection` and
   `read_datasets` answer what the pages show, under the data role's names
   (contract v20) -- the release, its days, its
   publication, every currency's instrument -- and core's
   `dashboard__list_datasets` lists `fed-board:daily` as the catalogue declares
   it: push and pull, weekly, New York's day ending at noon, public domain;
   and `fed-board:fed_h15` and `fed-board:fed_zero` as rates, daily and
   weekly, New York's day.
4. Licensed and entitled at the Data sources page: the reader is entitled.
5. Read back: the dollar's cash instrument on 2 October 2026 is priced in 19
   currencies, francs at 0.8293 in the franc's instrument; the euro's at
   1.1259 in the dollar's; each a close, version 1, the published time the
   Board's.
6. Wanted: a day not recorded, 25 September, is asked of the plugin, which
   reads the week before's release and records it against the want; the
   reader then reads it. A day not published yet, 8 October, is declined
   `source_silent`; the franc's own instrument, which H.10 never prices
   (the Board quotes francs per dollar, and nothing inverts it), `not_covered`.
7. `store lake` is e2e/expected.lake, each subject named by its ISO code;
   its `miss` line, the records the rates are about reported missing, is
   held apart: four a process, once a day each, and the harness restarts the
   plugin when it rewrites its configuration (`entitle`), so the count is
   four or a multiple of it.
8. A new container: it reads the release again and records nothing twice;
   the lake is unchanged.
"""

import json
import os
import subprocess
import sys
import time

PROJECT = "fed-board-e2e"
LOG = ".e2e/runner.log"
COMPONENTS = ".e2e/components.log"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", ".e2e/harness/compose.yaml",
           "-f", ".e2e/harness/plugins.yaml", "-f", "e2e/plugin.yaml"]
DATASET = "fed-board:daily"


class Failed(Exception):
    pass


def log(text):
    with open(LOG, "a", encoding="utf-8") as kept:
        kept.write(text + "\n")


def compose(*args, check=True, timeout=600):
    done = subprocess.run(COMPOSE + list(args), capture_output=True, text=True,
                          timeout=timeout)
    log(f"$ compose {' '.join(args)[:300]}\n{done.stdout[-4000:]}{done.stderr[-2000:]}")
    if check and done.returncode != 0:
        raise Failed(f"compose {' '.join(args)[:200]}: {(done.stdout + done.stderr).strip()[-600:]}")
    return done


def runner(*args, check=True):
    done = compose("run", "--rm", "-T", "runner", *args, check=check)
    return done.stdout if check else done


def must(condition, why):
    if not condition:
        raise Failed(why)


def until(seconds, attempt, what):
    deadline = time.monotonic() + seconds
    last = None
    while True:
        try:
            answer = attempt()
        except Failed as failed:
            answer, last = None, failed
        if answer:
            return answer
        if time.monotonic() > deadline:
            raise Failed(f"{what}, in {seconds} seconds" + (f": {last}" if last else ""))
        time.sleep(2)


def page(instance, level, path):
    said = runner("page", "--instance", instance, "--level", level, path)
    status, _, body = said.partition("\n")
    must(status.strip() == "200", f"{instance} {path} answered {said[-600:]}")
    return body


def prices(subject, day):
    """The reader's read of the plugin's dataset, by business date."""
    body = page("reader", "read", f"/prices?subject={subject}&date={day}&dataset={DATASET}&kind=close")
    return json.loads(body)


def call(tool, arguments=None):
    done = runner("mcp", "call", tool, json.dumps(arguments or {}), check=False)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        raise Failed(f"{tool}: no answer: {(done.stdout + done.stderr)[-400:]}")
    must(answer.get("outcome") in ("read", "unchanged"), f"{tool} answered {done.stdout[-700:]}")
    return answer["data"]


def store_lake():
    return compose("run", "--rm", "-T", "store", "lake").stdout


def misses(lines):
    """The misses `store lake` counts for the plugin: 0 where none."""
    found = [line.split("|")[2] for line in lines.splitlines() if line.startswith("miss|fed-board|")]
    return int(found[0]) if found else 0


def named(lines, codes):
    """`store lake` with each subject's ID, drawn per run, as its ISO code,
    and its misses held apart (`misses`)."""
    out = []
    for line in lines.strip().splitlines():
        parts = line.split("|")
        if parts[0] == "miss":
            continue
        if parts[0] == "row":
            parts[6] = codes.get(parts[6], parts[6])
        elif parts[0] == "want":
            parts[3] = ",".join(codes.get(s, s) for s in parts[3].split(","))
        out.append("|".join(parts))
    return "\n".join(sorted(out)) + "\n"


def run():
    started = time.time()
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    compose("up", "-d")
    runner("ready")
    runner("ready", "--instance", "reader")

    # 1. The Board unreachable.
    page_said = runner("page", "--level", "admin", "/", "--until", "Not answering",
                       "--seconds", "90")
    must("ConnectionRefusedError" in page_said or "URLError" in page_said or "Error" in page_said,
         f"step 1, Connection names why the Board was not reached: {page_said[-500:]}")
    lake = store_lake()
    must("row|" not in lake, f"step 1, nothing recorded with the Board unreachable: {lake}")

    # 2. Sample data: the release of 5 October 2026 recorded.
    runner("settings", "sample_data=true")
    runner("page", "--level", "admin", "/datasets?tab=currencies", "--until", 'data-code="VES"', "--seconds", "120")
    runner("page", "--level", "admin", "/?tab=sources", "--until", "Mon 05 Oct", "--seconds", "60")
    until(60, lambda: store_lake().count("row|fed-board:daily|price|") >= 115,
          "step 2, the release's 115 rates were not recorded")
    runner("page", "--level", "admin", "/?tab=sources", "--until", "Fri 16 Oct", "--seconds", "90")
    runner("page", "--level", "admin", "/?tab=sources", "--until", "Wed 21 Oct", "--seconds", "30")
    held = runner("page", "--level", "admin", "/datasets?tab=records", "--until", "reported missing",
                  "--seconds", "60")
    must("frb: feds200628" in held and "nyfed: EFFR" in held,
         f"step 2, Records lists the records the rates are about: {held[-600:]}")
    must("row|fed-board:fed_" not in store_lake(),
         "step 2, no rate recorded against a record the deployment does not hold")

    # 3. Parity through the deployment's MCP, and core's view of the catalogue.
    runner("grant", "--level", "admin")
    runner("mcp", "connect", "--covers", "deployment_admin", "--covers", "fed-board:admin")
    tools = runner("mcp", "list").split()
    read_connection = next((t for t in tools if t.endswith("read_connection")), "")
    read_datasets = next((t for t in tools if t.endswith("read_datasets")), "")
    must(read_connection and read_datasets, f"step 3, the plugin's two tools are listed: {tools}")
    connection = call(read_connection)
    must([s["latest"] for s in connection["sources"]] == ["2026-10-05", "2026-10-21", "2026-10-16"],
         f"step 3, read_connection's sources: {connection.get('sources')}")
    must(connection["latest_release"] == "2026-10-05" and connection["first_day"] == "2026-09-28"
         and connection["last_day"] == "2026-10-02" and connection["mode"] == "Sample data"
         and connection["credentials"] == [] and connection["sessions"] is None
         and connection["published_at"] == "2026-10-05T20:15:04+00:00",
         f"step 3, read_connection: {connection}")
    datasets = call(read_datasets)
    codes = {c["instrument_id"]: c["code"] for c in datasets["currencies"] if c["instrument_id"]}
    ids = {code: instrument for instrument, code in codes.items()}
    must(len(ids) == 24 and datasets["served"][0]["dataset"] == DATASET,
         f"step 3, read_datasets names 24 instruments: {datasets}")
    shown = page("fed-board", "admin", "/datasets?tab=currencies")
    must(all(instrument in shown for instrument in codes), "step 3, Datasets shows what read_datasets answers")
    listed = {d["dataset"]: d for d in call("dashboard__list_datasets")["datasets"]}
    entry = listed.get(DATASET, {}).get("catalogue_entry", {})
    must(entry.get("modes") == ["push", "pull"] and entry.get("day_time_zone") == "America/New_York"
         and entry.get("day_end_minute") == 720 and entry.get("cadence") == 604800,
         f"step 3, core lists the catalogue as declared: {listed.get(DATASET)}")
    for rates, cadence in (("fed-board:fed_h15", 86400), ("fed-board:fed_zero", 604800)):
        entry = listed.get(rates, {}).get("catalogue_entry", {})
        must(entry.get("cadence") == cadence and entry.get("day_time_zone") == "America/New_York"
             and "meridian.v1.Rate" in entry.get("data_types", []),
             f"step 3, core lists {rates} as declared: {listed.get(rates)}")

    # 4. Licensed and entitled.
    runner("licence", DATASET, "kept=true", "retention_days=0", "derived_use=true", "display=true",
           "personal_use=false", "note=Public domain: the Board's H.10.")
    runner("entitle", "--instance", "reader", DATASET, "note=The e2e's reader reads the rates.")
    runner("grant", "--instance", "reader", "--level", "read")

    # 5. Read back, in the right instruments.
    read = until(60, lambda: (lambda r: r if len(r["prices"]) == 19 else None)(prices(ids["USD"], "2026-10-02")),
                 "step 5, the dollar's 19 prices on 2 October were not read")
    franc = [p for p in read["prices"] if p["row_key"] == "CHF:2026-10-02"]
    must(franc and franc[0]["amount"] == "0.8293" and franc[0]["instrument_id"] == ids["CHF"]
         and franc[0]["kind"] == "PRICE_KIND_CLOSE" and franc[0]["version"] == 1
         and franc[0]["business_date"] == "2026-10-02"
         and franc[0]["published"] == [1791231304 * 10**9],
         f"step 5, the dollar priced in francs as the Board quotes it: {franc}")
    euro = prices(ids["EUR"], "2026-10-02")["prices"]
    must(len(euro) == 1 and euro[0]["amount"] == "1.1259" and euro[0]["instrument_id"] == ids["USD"],
         f"step 5, the euro priced in dollars as the Board quotes it: {euro}")

    # 6. Wants: a past week recorded against one; a week not published and a
    # subject not covered declined.
    asked = prices(ids["USD"], "2026-09-25")
    must(asked["prices"] or any(u["reason"] == "UNANSWERED_REASON_ASKED_SOURCE" for u in asked["unanswered"]),
         f"step 6, 25 September is asked of the plugin: {asked}")
    past = until(90, lambda: (lambda r: r if len(r["prices"]) == 19 else None)(prices(ids["USD"], "2026-09-25")),
                 "step 6, the week before was not recorded against the want")
    yen = [p for p in past["prices"] if p["row_key"] == "JPY:2026-09-25"]
    must(yen and yen[0]["instrument_id"] == ids["JPY"], f"step 6, the week before's yen: {yen}")
    prices(ids["EUR"], "2026-10-08")
    prices(ids["CHF"], "2026-10-02")
    until(90, lambda: "|declined|" in store_lake() and store_lake().count("|declined|") >= 2,
          "step 6, the week not published and the franc's instrument were not declined")

    # 7. The lake.
    lines = store_lake()
    count = misses(lines)
    must(count >= 4 and count % 4 == 0,
         f"step 7, the four records the rates are about reported missing, once a process: {count}")
    got = named(lines, codes)
    with open(".e2e/lake", "w", encoding="utf-8") as kept:
        kept.write(got)
    with open("e2e/expected.lake", encoding="utf-8") as held:
        expected = held.read()
    if got != expected:
        diff = subprocess.run(["diff", "-u", "e2e/expected.lake", ".e2e/lake"], capture_output=True, text=True)
        raise Failed(f"step 7, the lake is not e2e/expected.lake:\n{diff.stdout[-3000:]}")

    # 8. A new container records nothing twice.
    compose("up", "-d", "--no-deps", "--force-recreate", "fed-board")
    runner("ready")
    until(120, lambda: "Mon 05 Oct" in page("fed-board", "admin", "/?tab=sources"),
          "step 8, the new container did not read the release again")
    time.sleep(5)
    again = named(store_lake(), codes)
    must(again == got, "step 8, the new container recorded something twice:\n"
         + subprocess.run(["diff", "-u", "-", ".e2e/lake"], input=again, capture_output=True, text=True).stdout[-2000:])
    logs = compose("logs", "--no-color", "fed-board").stdout
    must("0 rates recorded, 0 restated, 115 unchanged" in logs,
         "step 8, the new container's check was answered unchanged: " + logs[-800:])
    until(90, lambda: all(s["licensed"] for s in call(read_datasets)["served"]),
          "step 8, the new container never read its dataset's licence")

    rows = got.count("row|")
    print(f"e2e OK in {int(time.time() - started)}s on the plugin harness: the Board unreachable said on "
          f"Connection, nothing recorded; sample data's release of 5 October 2026 recorded, 24 currencies "
          f"resolved; H.15's and the zero curve's files read, their records reported missing; "
          f"read_connection and read_datasets answering what the pages show, and core listing "
          f"its three datasets as declared; licensed and entitled; the dollar priced in 19 currencies (francs 0.8293) "
          f"and the euro in dollars (1.1259), each a close on its business date with the Board's published "
          f"time; 25 September wanted and recorded from the week before, 8 October declined source silent "
          f"and the franc's own instrument not covered; `store lake` as e2e/expected.lake ({rows} rows); "
          f"and a new container recording nothing twice, its licence read on start")


def main():
    os.makedirs(".e2e", exist_ok=True)
    open(LOG, "w").close()
    try:
        run()
    except (Failed, subprocess.TimeoutExpired, KeyError, ValueError, IndexError, TypeError) as failed:
        with open(COMPONENTS, "a", encoding="utf-8") as kept:
            kept.write(compose("logs", "--no-color", check=False).stdout)
        compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
        print(f"e2e FAILED: {failed}; the runner's log is in {LOG}, the components' in {COMPONENTS}",
              file=sys.stderr)
        return 1
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
