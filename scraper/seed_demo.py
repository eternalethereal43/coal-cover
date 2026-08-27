"""Generate a demo dataset so the dashboard renders before the first live run.

Anchor values are transcribed from the published report for 14 Jul 2026; the
preceding days are a random walk backwards from those figures. Everything here
is overwritten the first time `python -m scraper.cli update` succeeds. Files
carry `"demo": true` so the dashboard can label them.

    python -m scraper.seed_demo --days 21
"""
from __future__ import annotations

import argparse
import datetime as dt
import random

from . import build_site, normalize

# plant | state | utility | section | mode | MW | PLF% | days | req | norm |
# indigenous | import | receipt | consumption | remarks
ANCHOR = """
PANIPAT TPS|Haryana|HPGCL|A|RAIL|710|67|22|10.3|226.2|167.0|0.0|11.7|9.3|
RAJIV GANDHI TPS|Haryana|HPGCL|A|RAIL|1200|66|22|18.2|400.2|203.9|0.0|7.9|15.9|
YAMUNA NAGAR TPS|Haryana|HPGCL|A|RAIL|600|60|22|9.1|201.2|172.3|0.0|13.5|8.2|
GH TPS (LEH.MOH.)|Punjab|PSPCL|A|RAIL|920|80|22|11.7|258.1|303.9|0.0|20.4|12.0|
GOINDWAL SAHIB TPP|Punjab|PSPCL|A|RAIL|540|75|22|6.6|145.9|135.3|0.0|11.8|6.2|
ROPAR TPS|Punjab|PSPCL|A|RAIL|840|51|22|11.2|247.3|442.1|0.0|3.9|8.3|
CHHABRA-II TPP|Rajasthan|RRVUNL|A|RAIL|1320|68|22|17.1|375.6|166.6|0.0|15.4|15.1|
KALISINDH TPS|Rajasthan|RRVUNL|A|RAIL|1200|73|22|16.0|351.7|212.2|0.0|7.7|15.5|
KOTA TPS|Rajasthan|RRVUNL|A|RAIL|1240|61|22|18.6|409.6|208.0|0.0|19.0|14.7|
SURATGARH STPS|Rajasthan|RRVUNL|A|RAIL|1320|72|22|16.8|369.1|216.1|0.0|0.0|14.0|
SURATGARH TPS|Rajasthan|RRVUNL|A|RAIL|1500|51|22|21.8|479.3|186.6|0.0|11.0|12.0|
ANPARA TPS|Uttar Pradesh|UPRVUNL|A|PITHEAD|2630|76|14|37.8|529.5|281.7|0.0|26.7|51.1|
HARDUAGANJ TPS|Uttar Pradesh|UPRVUNL|A|RAIL|1265|46|22|18.0|396.3|190.7|0.0|3.8|11.5|
JAWAHARPUR STPP|Uttar Pradesh|UPRVUNL|A|RAIL|1320|55|22|17.1|375.6|228.3|0.0|7.8|12.8|
OBRA TPS|Uttar Pradesh|UPRVUNL|A|RAIL|2320|60|22|36.0|791.3|286.2|0.0|10.5|22.8|
PANKI TPS EXT|Uttar Pradesh|UPRVUNL|A|RAIL|660|70|22|9.0|198.5|57.5|0.0|7.1|7.9|
PARICHHA TPS|Uttar Pradesh|UPRVUNL|A|RAIL|920|54|22|14.3|314.2|98.9|0.0|8.1|11.6|
DSPM TPS|Chhatisgarh|CSPGCL|A|RAIL|500|66|22|7.3|160.2|346.8|0.0|6.2|2.0|
KORBA-WEST TPS|Chhatisgarh|CSPGCL|A|PITHEAD|1340|68|14|21.3|298.9|567.1|0.0|16.7|19.0|
MARWA TPS|Chhatisgarh|CSPGCL|A|RAIL|1000|80|22|15.9|350.1|555.0|0.0|18.8|16.1|
GANDHI NAGAR TPS|Gujarat|GSECL|A|RAIL|630|61|22|9.4|205.8|56.9|0.0|5.5|8.8|
UKAI TPS|Gujarat|GSECL|A|RAIL|1110|40|22|16.5|363.2|229.0|0.0|3.0|7.8|
WANAKBORI TPS|Gujarat|GSECL|A|RAIL|2270|58|22|31.7|697.9|106.7|0.0|27.2|29.3|Railways to supply rakes on a consistent basis from washeries and GSS from SECL
SANJAY GANDHI TPS|Madhya Pradesh|MPPGCL|A|RAIL|1340|69|22|17.9|392.7|268.8|0.0|3.6|16.2|
SATPURA TPS|Madhya Pradesh|MPPGCL|A|RAIL|500|83|22|6.7|147.9|111.5|0.0|3.8|7.2|
SHREE SINGAJI TPP|Madhya Pradesh|MPPGCL|A|RAIL|2520|72|22|34.5|758.9|111.2|0.0|34.0|34.0|Railways to supply rakes as per sub group plan
BHUSAWAL TPS|Maharashtra|MAHAGENCO|A|RAIL|1870|50|22|30.6|673.1|266.9|0.0|35.6|11.4|
CHANDRAPUR(MAHARASHTRA) STPS|Maharashtra|MAHAGENCO|A|RAIL|2920|52|22|47.8|1052.3|710.5|87.6|36.8|32.5|
KHAPARKHEDA TPS|Maharashtra|MAHAGENCO|A|RAIL|1340|56|22|23.3|511.8|211.8|46.0|12.1|18.3|
KORADI TPS|Maharashtra|MAHAGENCO|A|RAIL|2190|64|22|33.5|737.2|235.1|8.8|28.4|31.9|
NASIK TPS|Maharashtra|MAHAGENCO|A|RAIL|630|40|22|12.2|267.8|77.3|72.8|3.9|8.2|
PARLI TPS|Maharashtra|MAHAGENCO|A|RAIL|750|66|22|11.9|261.9|122.9|0.0|7.8|10.6|
Dr. N.TATA RAO TPS|Andhra Pradesh|APGENCO|A|RAIL|2560|68|22|42.0|924.9|168.4|0.0|16.6|33.9|ECL and railways to ensure coal supply as per subgroup plan
RAYALASEEMA TPS|Andhra Pradesh|APGENCO|A|RAIL|1650|54|22|28.0|615.4|123.8|0.0|16.7|21.0|ECL and railways to ensure coal supply as per subgroup plan
DAMODARAM SANJEEVAIAH TPS|Andhra Pradesh|APPDCL|A|RAIL-SEA|2400|56|22|32.0|704.4|64.9|0.0|13.4|23.5|GENCO to ensure sufficient rail programme in ECL and MCL
BELLARY TPS|Karnataka|KPCL|A|RAIL|1700|56|22|25.8|568.4|358.4|0.0|23.5|22.9|
RAICHUR TPS|Karnataka|KPCL|A|RAIL|1720|48|22|27.5|605.2|305.1|0.0|19.2|18.1|
YERMARUS TPP|Karnataka|RPCL|A|RAIL|1600|70|22|22.4|491.9|242.7|0.0|19.9|18.6|
METTUR TPS|Tamil Nadu|TANGEDCO|A|RAIL-SEA-RAIL|840|77|22|14.5|318.2|169.2|0.0|14.4|10.9|
NORTH CHENNAI TPS STAGE 2|Tamil Nadu|TANGEDCO|A|RAIL-SEA|1200|52|22|20.7|454.5|98.1|0.0|22.7|4.8|GENCO to liquidate coal lying at the port and in transit
NORTH CHENNAI TPS STAGE 3|Tamil Nadu|TANGEDCO|A|RAIL|800|55|22|10.9|240.6|61.5|143.5|4.1|8.0|
TUTICORIN TPS|Tamil Nadu|TANGEDCO|A|RAIL-SEA|1050|46|22|19.1|419.9|155.0|0.0|0.0|11.8|
SINGARENI TPP|Telangana|SCCL|A|RAIL|1200|72|22|15.6|343.1|99.9|0.0|15.1|17.1|
BHADRADRI TPP|Telangana|TSGENCO|A|ROAD|1080|53|22|16.2|355.8|118.3|0.0|11.5|11.2|
KAKATIYA TPS|Telangana|TSGENCO|A|ROAD|1100|69|22|12.7|279.9|93.2|0.0|4.9|10.8|
YADADRI TPS|Telangana|TSGENCO|A|RAIL|3200|24|22|43.7|962.2|156.4|0.0|14.0|11.0|SCCL to ensure supply of coal as per subgroup plan
TENUGHAT TPS|Jharkhand|TVNL|A|RAIL|420|74|22|6.3|139.5|236.2|0.0|3.7|6.0|
IB VALLEY TPS|Odisha|OPGC|A|PITHEAD|1740|87|14|25.3|354.3|330.2|0.0|27.7|26.3|
D.P.L. TPS|West Bengal|DPL|A|RAIL|550|71|22|8.1|179.0|32.9|0.0|3.9|3.9|Plant to augment coal supplies from its captive mines
BAKRESWAR TPS|West Bengal|WBPDC|A|RAIL|1050|86|22|13.4|295.0|127.6|0.0|11.2|15.1|
KOLAGHAT TPS|West Bengal|WBPDC|A|RAIL|840|56|22|11.9|262.8|151.6|0.0|15.2|10.0|
SAGARDIGHI TPS|West Bengal|WBPDC|A|RAIL|2260|88|22|30.2|664.4|468.7|0.0|18.2|31.6|
SANTALDIH TPS|West Bengal|WBPDC|A|RAIL|500|88|22|6.4|140.7|82.0|0.0|0.0|7.5|
GHATAMPUR TPP|Uttar Pradesh|NUPPL|A|RAIL|1980|24|22|27.1|595.4|178.7|0.0|19.2|9.1|
KHURJA TPP|Uttar Pradesh|THDC|A|RAIL|1320|87|22|18.0|396.9|146.1|0.0|15.0|15.2|
BUXAR TPP|Bihar|SJVNL|A|RAIL|660|72|22|9.0|198.5|59.4|0.0|9.1|8.6|CCL to ensure supply of coal as per subgroup plan
DADRI (NCTPP)|Uttar Pradesh|NTPC|A|RAIL|1840|60|22|26.5|583.0|479.3|0.0|15.1|19.1|
RIHAND STPS|Uttar Pradesh|NTPC|A|PITHEAD|3000|85|14|38.6|540.6|662.1|0.0|44.1|39.7|
SINGRAULI STPS|Uttar Pradesh|NTPC|A|PITHEAD|2000|86|14|28.4|397.0|286.6|0.0|30.1|30.0|
TANDA TPS|Uttar Pradesh|NTPC|A|RAIL|1760|55|22|23.1|507.9|237.0|0.0|11.5|17.3|
UNCHAHAR TPS|Uttar Pradesh|NTPC|A|RAIL|1550|71|22|22.6|497.4|349.3|0.0|20.8|21.3|
GADARWARA TPP|Madhya Pradesh|NTPC|A|RAIL|1600|76|22|22.6|497.6|186.1|0.0|27.5|10.9|
KHARGONE STPP|Madhya Pradesh|NTPC|A|RAIL|1320|73|22|18.5|406.4|198.8|0.0|15.1|18.2|
KORBA STPS|Chhatisgarh|NTPC|A|PITHEAD|2600|82|14|36.5|511.6|568.7|0.0|29.9|43.0|
LARA TPP|Chhatisgarh|NTPC|A|PITHEAD|1600|74|14|21.1|294.7|552.7|0.0|17.0|21.1|
MAUDA TPS|Maharashtra|NTPC|A|RAIL|2320|73|22|34.7|764.3|288.5|0.0|30.3|26.2|
SIPAT STPS|Chhatisgarh|NTPC|A|PITHEAD|2980|62|14|39.6|554.1|836.1|0.0|31.4|31.9|
SOLAPUR STPS|Maharashtra|NTPC|A|RAIL|1320|40|22|20.7|456.2|213.2|0.0|4.0|7.8|
VINDHYACHAL STPS|Madhya Pradesh|NTPC|A|PITHEAD|4760|74|14|68.4|957.1|877.7|0.0|68.3|72.9|
KUDGI STPP|Karnataka|NTPC|A|RAIL|2400|65|22|35.5|780.9|261.9|0.0|17.9|30.7|
RAMAGUNDEM STPS|Telangana|NTPC|A|PITHEAD|2600|40|14|34.8|487.9|518.1|0.0|16.0|31.5|
SIMHADRI|Andhra Pradesh|NTPC|A|RAIL|2000|79|22|31.3|687.6|372.7|0.0|19.0|29.7|
BARH STPS|Bihar|NTPC|A|RAIL|3300|56|22|45.9|1010.1|858.2|0.0|29.6|27.6|
DARLIPALI STPS|Odisha|NTPC|A|PITHEAD|1600|81|14|22.7|318.0|521.3|0.0|22.1|25.5|
FARAKKA STPS|West Bengal|NTPC|A|PITHEAD|2100|64|14|29.8|417.4|529.0|0.0|12.4|27.4|
KAHALGAON TPS|Bihar|NTPC|A|PITHEAD|2340|79|14|38.8|543.3|446.9|0.0|35.0|41.9|
NABINAGAR STPP|Bihar|NTPC|A|RAIL|1980|70|22|26.3|578.5|375.0|0.0|3.5|27.0|
NORTH KARANPURA TPP|Jharkhand|NTPC|A|PITHEAD|1980|77|14|28.4|397.5|591.0|0.0|23.0|29.8|
TALCHER STPS|Odisha|NTPC|A|PITHEAD|3000|66|14|45.8|640.9|527.8|0.0|43.2|45.1|
INDIRA GANDHI STPP|Haryana|NTPC JV|A|RAIL|1500|66|22|21.2|466.5|345.3|0.0|7.4|18.5|
MEJA STPP|Uttar Pradesh|NTPC JV|A|RAIL|1320|79|22|17.9|392.8|221.9|0.0|15.5|19.6|
VALLUR TPP|Tamil Nadu|NTPC JV|A|RAIL-SEA|1500|51|22|24.9|547.3|342.6|0.0|0.0|16.0|
PATRATU STPP|Jharkhand|NTPC JV|A|RAIL|1600|23|22|21.9|481.1|400.8|0.0|13.5|13.6|
BOKARO TPS `A` EXP|Jharkhand|DVC|A|RAIL|500|86|22|6.4|141.8|206.2|0.0|0.0|6.9|
DURGAPUR STEEL TPS|West Bengal|DVC|A|RAIL|1000|76|22|13.2|289.5|233.3|0.0|18.2|12.5|
MEJIA TPS|West Bengal|DVC|A|RAIL|2340|72|22|31.4|691.0|420.3|0.0|35.1|28.0|
RAGHUNATHPUR TPP|West Bengal|DVC|A|RAIL|1200|41|22|16.9|372.1|450.1|0.0|7.2|8.2|
ADANI POWER LIMITED KAWAI TPP|Rajasthan|IPP|A|RAIL|1320|82|22|15.3|336.5|102.1|70.5|23.8|16.1|
ADANI POWER LIMITED RAIPUR TPP|Chhatisgarh|IPP|A|RAIL|1370|80|22|19.3|423.6|94.4|0.0|25.6|20.7|SECL to ensure supply as per subgroup plan
ADANI POWER LIMITED TIRODA TPP|Maharashtra|IPP|A|RAIL|3300|66|22|43.4|955.3|107.2|62.4|36.2|36.8|Railways to supply rakes on priority as per sub group allocation
AMRAVATI TPS|Maharashtra|IPP|A|RAIL|1350|74|22|18.0|395.6|102.2|0.0|8.8|16.8|
ANPARA C TPS|Uttar Pradesh|IPP|A|PITHEAD|1200|60|14|15.5|217.6|42.1|0.0|10.0|8.9|NCL to ensure supply of coal as per subgroup plan
BALCO TPS|Chhatisgarh|IPP|A|RAIL|600|80|22|7.4|162.4|68.0|0.0|3.8|4.3|
BUTIBORI TPP|Maharashtra|IPP|A|ROAD|600|80|22|8.2|180.4|21.2|0.0|1.8|9.7|SECL to ensure supply as per subgroup plan
DAHANU TPS|Maharashtra|IPP|A|RAIL|500|64|22|7.1|156.6|9.7|43.1|4.0|6.7|SECL to ensure supply as per subgroup plan
DERANG TPP|Odisha|IPP|A|ROAD|1200|81|22|17.6|387.8|976.8|0.0|23.2|19.0|
JSW Energy Utkal Limited|Odisha|IPP|A|RAIL|700|76|22|12.0|263.6|70.5|0.0|15.9|13.7|
LALITPUR TPS|Uttar Pradesh|IPP|A|RAIL|1980|75|22|25.4|558.1|464.6|0.0|31.0|24.0|
MAHAN TPP|Madhya Pradesh|IPP|A|RAIL|1200|77|22|14.9|328.0|84.7|0.0|17.8|16.4|
OP JINDAL TPS|Chhatisgarh|IPP|A|ROAD|1000|92|22|15.9|349.6|561.3|0.0|18.9|14.7|
PRAYAGRAJ TPP|Uttar Pradesh|IPP|A|RAIL|1980|81|22|23.4|515.4|347.2|0.0|23.0|25.1|
RAJPURA TPP|Punjab|IPP|A|RAIL|1400|88|22|16.0|352.5|378.4|0.0|15.2|17.2|
SASAN UMTPP|Madhya Pradesh|IPP|A|PITHEAD|3960|85|14|47.3|661.6|47.8|0.0|55.8|51.6|Plant to lift coal from its captive mine
TALWANDI SABO TPP|Punjab|IPP|A|RAIL|1980|66|22|25.0|550.9|403.3|0.0|14.0|31.0|
TAMNAR TPP|Chhatisgarh|IPP|A|ROAD|2400|64|22|38.4|844.5|406.8|1.7|44.4|34.7|
UCHPINDA TPP|Chhatisgarh|IPP|A|RAIL|1440|79|22|21.6|475.7|149.6|0.0|20.5|20.9|
VIZAG TPP|Andhra Pradesh|IPP|A|RAIL|1040|64|22|17.5|384.6|121.4|0.0|11.6|10.2|
SIKKA REP. TPS|Gujarat|GSECL|B|Sea|500|10|22|5.3|117.1|3.6|61.7|0.0|0.0|
ADANI POWER LIMITED MUNDRA TPP - I & II|Gujarat|IPP|B|Sea|2640|34|22|29.6|650.5|0.0|81.0|14.6|11.1|Plant to build up stock through import
ADANI POWER LIMITED UDUPI TPP|Karnataka|IPP|B|Sea|1200|56|22|10.4|228.3|0.0|25.1|10.3|7.4|Plant to build up stock through import
ITPCL TPP|Tamil Nadu|IPP|B|Sea|1200|70|22|14.1|309.1|0.0|331.2|13.5|13.0|
MUNDRA UMTPP|Gujarat|IPP|B|Sea|4000|70|22|32.9|723.5|0.0|1128.6|65.3|29.4|
TROMBAY TPS|Maharashtra|IPP|B|Sea|750|55|22|9.7|214.1|0.0|168.7|7.6|7.7|
MIHAN TPS|Maharashtra|IPP|C|RAIL|246|0|22|3.4|74.0|0.0|0.0|0.0|0.0|not in operation
KASAIPALLI TPP|Chhatisgarh|IPP|D|ROAD|270|27|22|5.3|116.6|17.7|0.0|2.6|2.8|Plant based on washery rejects
RATIJA TPS|Chhatisgarh|IPP|D|ROAD|100|52|22|2.6|57.1|9.0|0.0|2.4|1.3|Plant based on washery rejects
"""


def _rows():
    for i, line in enumerate(l for l in ANCHOR.strip().splitlines() if l.strip()):
        f = line.split("|")
        yield {
            "sl_no": float(i + 1),
            "plant": f[0], "state": f[1], "utility": f[2], "section": f[3],
            "mode_of_transport": f[4], "capacity_mw": float(f[5]),
            "plf_pct": float(f[6]), "norm_days": float(f[7]),
            "daily_req_kt": float(f[8]), "norm_stock_kt": float(f[9]),
            "stock_indigenous_kt": float(f[10]), "stock_import_kt": float(f[11]),
            "receipt_kt": float(f[12]), "consumption_kt": float(f[13]),
            "remarks": f[14] if len(f) > 14 else "",
        }


def build(days: int = 21, seed: int = 7) -> None:
    rng = random.Random(seed)
    anchor_date = dt.date(2026, 7, 14)
    base = list(_rows())
    # State carried backwards from the anchor day.
    state = {r["plant"]: r["stock_indigenous_kt"] + r["stock_import_kt"] for r in base}

    for back in range(days):
        day = anchor_date - dt.timedelta(days=back)
        plants = []
        for r in base:
            rec = dict(r)
            rec["date"] = day.isoformat()
            rec["section_name"] = {"A": "Domestic coal (linkage, no linkage, coal block)",
                                   "B": "Designed on imported coal",
                                   "C": "Not in operation",
                                   "D": "Based on washery rejects"}[r["section"]]
            total = max(0.0, state[r["plant"]])
            imp_share = (r["stock_import_kt"] /
                         (r["stock_indigenous_kt"] + r["stock_import_kt"] or 1))
            rec["stock_total_kt"] = round(total, 1)
            rec["stock_import_kt"] = round(total * imp_share, 1)
            rec["stock_indigenous_kt"] = round(total - rec["stock_import_kt"], 1)
            rec["pct_of_norm"] = round(100 * total / r["norm_stock_kt"], 1) if r["norm_stock_kt"] else None
            rec["critical_flag"] = bool(rec["pct_of_norm"] and rec["pct_of_norm"] < 25)
            rec["receipt_kt"] = round(max(0.0, r["receipt_kt"] * rng.uniform(0.55, 1.5)), 1)
            rec["consumption_kt"] = round(max(0.0, r["consumption_kt"] * rng.uniform(0.85, 1.15)), 1)
            plants.append(rec)
            # Step one day further into the past.
            state[r["plant"]] = total - rec["receipt_kt"] + rec["consumption_kt"]

        payload = normalize.normalise_day({
            "date": day.isoformat(), "source": "demo", "column_confidence": 1.0,
            "plants": plants,
        })
        payload["demo"] = True
        build_site.write_day(payload)

    build_site.rebuild_indexes(None)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    build(ap.parse_args().days)
