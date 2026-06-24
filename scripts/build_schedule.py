"""
Build data/schedule.csv — the authoritative WC2026 match schedule.

Static reference data (the schedule does not change), encoded once here so it is
reproducible and reviewable. Source: the official FIFA 2026 match schedule
(venues + kick-off times, all listed in US Eastern). Group-stage match numbers
1-72 and Round-of-32 numbers 73-88 map exactly onto src/wc2026/structure.py;
Round-of-16 through the Final (89-104) follow FIFA's chronological numbering.

Kick-off times are stored as an absolute UTC instant; the site converts that to
US Eastern, Brasília, and Amsterdam in the browser (DST-correct). The whole
tournament (11 Jun – 19 Jul 2026) sits inside US EDT (UTC-4), so UTC = ET + 4h.

    python scripts/build_schedule.py        # writes data/schedule.csv
"""
import os, csv, datetime as dt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "data", "schedule.csv")

# venue key -> (stadium, city, state/province, country)
VEN = {
    "azteca":   ("Estadio Azteca", "Mexico City", "Ciudad de México", "Mexico"),
    "akron":    ("Estadio Akron", "Zapopan", "Jalisco", "Mexico"),
    "bbva":     ("Estadio BBVA", "Monterrey", "Nuevo León", "Mexico"),
    "bmo":      ("BMO Field", "Toronto", "Ontario", "Canada"),
    "bcplace":  ("BC Place", "Vancouver", "British Columbia", "Canada"),
    "sofi":     ("SoFi Stadium", "Inglewood", "California", "United States"),
    "levis":    ("Levi's Stadium", "Santa Clara", "California", "United States"),
    "lumen":    ("Lumen Field", "Seattle", "Washington", "United States"),
    "metlife":  ("MetLife Stadium", "East Rutherford", "New Jersey", "United States"),
    "gillette": ("Gillette Stadium", "Foxborough", "Massachusetts", "United States"),
    "nrg":      ("NRG Stadium", "Houston", "Texas", "United States"),
    "att":      ("AT&T Stadium", "Arlington", "Texas", "United States"),
    "lincoln":  ("Lincoln Financial Field", "Philadelphia", "Pennsylvania", "United States"),
    "mercedes": ("Mercedes-Benz Stadium", "Atlanta", "Georgia", "United States"),
    "hardrock": ("Hard Rock Stadium", "Miami Gardens", "Florida", "United States"),
    "arrowhead":("Arrowhead Stadium", "Kansas City", "Missouri", "United States"),
}

# (match_no, date, ET kick-off HH:MM, venue key)
SCHED = [
    (1,"2026-06-11","15:00","azteca"),(2,"2026-06-11","22:00","akron"),
    (3,"2026-06-12","15:00","bmo"),(4,"2026-06-12","21:00","sofi"),
    (5,"2026-06-13","15:00","levis"),(6,"2026-06-13","18:00","metlife"),(7,"2026-06-13","21:00","gillette"),
    (8,"2026-06-14","12:00","bcplace"),(9,"2026-06-14","13:00","nrg"),(10,"2026-06-14","16:00","att"),
    (11,"2026-06-14","19:00","lincoln"),(12,"2026-06-14","22:00","bbva"),
    (13,"2026-06-15","12:00","mercedes"),(14,"2026-06-15","15:00","lumen"),(15,"2026-06-15","18:00","hardrock"),(16,"2026-06-15","21:00","sofi"),
    (17,"2026-06-16","15:00","metlife"),(18,"2026-06-16","18:00","gillette"),(19,"2026-06-16","21:00","arrowhead"),
    (20,"2026-06-17","00:00","levis"),(21,"2026-06-17","13:00","nrg"),(22,"2026-06-17","16:00","att"),(23,"2026-06-17","19:00","bmo"),(24,"2026-06-17","22:00","azteca"),
    (25,"2026-06-18","12:00","mercedes"),(26,"2026-06-18","15:00","sofi"),(27,"2026-06-18","18:00","bcplace"),(28,"2026-06-18","21:00","akron"),
    (29,"2026-06-19","15:00","lumen"),(30,"2026-06-19","18:00","gillette"),(31,"2026-06-19","20:30","lincoln"),(32,"2026-06-19","23:00","levis"),
    (33,"2026-06-20","13:00","nrg"),(34,"2026-06-20","16:00","bmo"),(35,"2026-06-20","20:00","arrowhead"),
    (36,"2026-06-21","00:00","bbva"),(37,"2026-06-21","12:00","mercedes"),(38,"2026-06-21","15:00","sofi"),(39,"2026-06-21","18:00","hardrock"),(40,"2026-06-21","21:00","bcplace"),
    (41,"2026-06-22","13:00","att"),(42,"2026-06-22","17:00","lincoln"),(43,"2026-06-22","20:00","metlife"),(44,"2026-06-22","23:00","levis"),
    (45,"2026-06-23","13:00","nrg"),(46,"2026-06-23","16:00","gillette"),(47,"2026-06-23","19:00","bmo"),(48,"2026-06-23","22:00","akron"),
    (49,"2026-06-24","15:00","bcplace"),(50,"2026-06-24","15:00","lumen"),(51,"2026-06-24","18:00","hardrock"),(52,"2026-06-24","18:00","mercedes"),(53,"2026-06-24","21:00","azteca"),(54,"2026-06-24","21:00","bbva"),
    (55,"2026-06-25","16:00","metlife"),(56,"2026-06-25","16:00","lincoln"),(57,"2026-06-25","19:00","att"),(58,"2026-06-25","19:00","arrowhead"),(59,"2026-06-25","22:00","sofi"),(60,"2026-06-25","22:00","levis"),
    (61,"2026-06-26","15:00","gillette"),(62,"2026-06-26","15:00","bmo"),(63,"2026-06-26","20:00","nrg"),(64,"2026-06-26","20:00","akron"),(65,"2026-06-26","23:00","lumen"),(66,"2026-06-26","23:00","bcplace"),
    (67,"2026-06-27","17:00","metlife"),(68,"2026-06-27","17:00","lincoln"),(69,"2026-06-27","19:30","hardrock"),(70,"2026-06-27","19:30","mercedes"),(71,"2026-06-27","22:00","arrowhead"),(72,"2026-06-27","22:00","att"),
    # Round of 32
    (73,"2026-06-28","15:00","sofi"),
    (74,"2026-06-29","16:30","gillette"),(75,"2026-06-29","21:00","bbva"),(76,"2026-06-29","13:00","nrg"),
    (77,"2026-06-30","17:00","metlife"),(78,"2026-06-30","13:00","att"),(79,"2026-06-30","21:00","azteca"),
    (80,"2026-07-01","12:00","mercedes"),(81,"2026-07-01","20:00","levis"),(82,"2026-07-01","16:00","lumen"),
    (83,"2026-07-02","19:00","bmo"),(84,"2026-07-02","15:00","sofi"),(85,"2026-07-02","23:00","bcplace"),
    (86,"2026-07-03","18:00","hardrock"),(87,"2026-07-03","21:30","arrowhead"),(88,"2026-07-03","14:00","att"),
    # Round of 16
    (89,"2026-07-04","13:00","nrg"),(90,"2026-07-04","17:00","lincoln"),
    (91,"2026-07-05","16:00","metlife"),(92,"2026-07-05","20:00","azteca"),
    (93,"2026-07-06","15:00","att"),(94,"2026-07-06","20:00","lumen"),
    (95,"2026-07-07","12:00","mercedes"),(96,"2026-07-07","16:00","bcplace"),
    # Quarter-finals
    (97,"2026-07-09","16:00","gillette"),(98,"2026-07-10","15:00","sofi"),
    (99,"2026-07-11","17:00","hardrock"),(100,"2026-07-11","21:00","arrowhead"),
    # Semi-finals, third place, final
    (101,"2026-07-14","15:00","att"),(102,"2026-07-15","15:00","mercedes"),
    (103,"2026-07-18","17:00","hardrock"),(104,"2026-07-19","15:00","metlife"),
]

EDT_OFFSET = dt.timedelta(hours=4)  # ET (EDT, UTC-4) -> UTC for the whole tournament


def main():
    rows = []
    for no, date, et, vk in SCHED:
        name, city, state, country = VEN[vk]
        local = dt.datetime.strptime(date + " " + et, "%Y-%m-%d %H:%M")
        utc = local + EDT_OFFSET
        rows.append({"match": no, "date": date, "et": et,
                     "utc": utc.strftime("%Y-%m-%dT%H:%MZ"),
                     "venue": name, "city": city, "state": state, "country": country})
    assert len(rows) == 104, f"expected 104 matches, got {len(rows)}"
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["match", "date", "et", "utc", "venue", "city", "state", "country"])
        w.writeheader()
        w.writerows(rows)
    print(f"  schedule -> {os.path.relpath(OUT, ROOT)}  ({len(rows)} matches)")


if __name__ == "__main__":
    main()
