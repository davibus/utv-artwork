import random
import csv

# -----------------------------
# SEARCH COMPONENTS
# -----------------------------

vehicles = [
    "UTV",
    "Side by Side",
    "SxS",
    "Custom UTV",
    "Modified UTV",
    "Off Road UTV",
    "Race UTV",
    "Rock Crawler UTV",
    "Polaris RZR",
    "Polaris RZR Pro R",
    "Polaris RZR Turbo R",
    "Can-Am Maverick R",
    "Can-Am X3",
    "Honda Talon",
    "Kawasaki KRX",
    "Yamaha YXZ",
    "Yamaha Wolverine",
    "Segway Villain"
]

actions = [
    "racing",
    "jumping",
    "big jump",
    "airborne",
    "rock crawling",
    "climbing rocks",
    "drifting",
    "powersliding",
    "throwing dirt",
    "roost",
    "high speed",
    "cornering",
    "wheelie",
    "mud bogging",
    "river crossing",
    "hill climbing",
    "dune jumping",
    "trail riding",
    "crash",
    "rollover",
    "flip",
    "wreck",
    "recovery",
    "stuck",
    "off road racing"
]

terrain = [
    "desert",
    "sand dunes",
    "rocks",
    "mountains",
    "mud",
    "deep mud",
    "forest",
    "snow",
    "river",
    "creek",
    "canyon",
    "slickrock",
    "dirt trail",
    "race track",
    "rock ledge"
]

visuals = [
    "dust",
    "huge dust cloud",
    "mud flying",
    "dirt flying",
    "dramatic",
    "cinematic",
    "extreme",
    "aggressive",
    "close up",
    "action shot",
    "hero shot",
    "wide angle",
    "low angle",
    "sunset",
    "golden hour",
    "night",
    "neon lights",
    "motion blur",
    "huge tires",
    "custom wheels",
    "lifted",
    "custom suspension",
    "long travel suspension",
    "LED lights"
]

locations = [
    "Moab Utah",
    "Sand Hollow Utah",
    "Little Sahara Utah",
    "Glamis",
    "Dumont Dunes",
    "Johnson Valley",
    "Baja",
    "Arizona desert",
    "Utah desert",
    "California desert"
]

events = [
    "King of the Hammers",
    "Baja 1000",
    "Mint 400",
    "Dakar Rally",
    "SCORE Racing"
]

image_modifiers = [
    "high resolution",
    "4K",
    "HD",
    "photography",
    "action photography",
    "wallpaper",
    "large image"
]


# -----------------------------
# QUERY GENERATOR
# -----------------------------

queries = set()

# Vehicle + action
for vehicle in vehicles:
    for action in actions:
        queries.add(f"{vehicle} {action}")

# Vehicle + action + terrain
for vehicle in vehicles:
    for action in actions:
        for ground in random.sample(terrain, min(5, len(terrain))):
            queries.add(f"{vehicle} {action} {ground}")

# Vehicle + action + visual
for vehicle in vehicles:
    for action in actions:
        for visual in random.sample(visuals, min(5, len(visuals))):
            queries.add(f"{vehicle} {action} {visual}")

# Vehicle + terrain + visual
for vehicle in vehicles:
    for ground in terrain:
        for visual in random.sample(visuals, min(4, len(visuals))):
            queries.add(f"{vehicle} {ground} {visual}")

# Vehicle + action + location
for vehicle in vehicles:
    for action in random.sample(actions, min(10, len(actions))):
        for location in locations:
            queries.add(f"{vehicle} {action} {location}")

# Event searches
for vehicle in vehicles:
    for event in events:
        queries.add(f"{vehicle} {event}")
        queries.add(f"{vehicle} racing {event}")
        queries.add(f"{vehicle} action {event}")

# High-resolution variations
base_queries = list(queries)

for query in random.sample(base_queries, min(500, len(base_queries))):
    modifier = random.choice(image_modifiers)
    queries.add(f"{query} {modifier}")


# -----------------------------
# EXPORT RESULTS
# -----------------------------

queries = sorted(queries)

print(f"Generated {len(queries):,} unique UTV search queries.")

# TXT file
with open("utv-search-queries.txt", "w", encoding="utf-8") as f:
    for query in queries:
        f.write(query + "\n")

# CSV file
with open("utv-search-queries.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["search_query"])

    for query in queries:
        writer.writerow([query])

print("Created:")
print("  utv-search-queries.txt")
print("  utv-search-queries.csv")