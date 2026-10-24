# Troubleshooting

## Reaching the Board

| What you see | What it means | What to do |
|---|---|---|
| **Not answering** | No check has reached the Board's site: no network, a proxy, or the site down | Check the deployment's outbound access to www.federalreserve.gov; the plugin tries again every hour |
| **Answering**, with a warning | An earlier check worked; the last did not | Nothing, usually: the next check runs within the hour. Connection's Sources tab says what failed |
| The H.10 backfill stops | The Board stopped answering during the first run's backfill | Nothing: it carries on an hour later, from where it stopped |

## Currencies and records

| What you see | What it means | What to do |
|---|---|---|
| **N currencies not resolved** | A currency's ISO 4217 code found no cash instrument, or two | Complete or merge the instrument at the Instruments page; the next check records its rates |
| A currency the plugin cannot name | The Board printed a currency this version has no code for | Its rates are not recorded; a new version adds it |
| Records: **none** | The deployment does not hold a record the platform seeds | Pull it from the platform at the Instruments page; the next day's check, or a restart, records its rates |

## Wants and licences

| What you see | What it means | What to do |
|---|---|---|
| Declined, *source silent* | The Board has not published that day or week yet | Wait for the next release |
| Declined, *not covered* | The dataset never states that subject; H.10 prices the dollar in a currency quoted per dollar | Read the dataset that states it, or invert in the reader |
| **Not licensed yet** | No deployment admin has licensed the dataset | Ask one to license it on Data sources; the page says so within a minute |
