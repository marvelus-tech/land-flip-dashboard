# Luxury Teardown Wholesaling — Florida Reverse Engineering

Source: https://youtu.be/wcLXKGEFDlI?si=_0f1FK-xH31RmlSk

## Core Approach

Traditional wholesalers are trained to lowball (65 cents on the dollar). The luxury teardown play does the opposite: **offer sellers MORE than Zillow says their home is worth** and still walk away with a six-figure assignment fee.

### Why It Works

- **Zillow estimates are wrong for teardown candidates.** Zestimate is built from the existing structure: square footage × average price per square foot in the neighborhood.
- The **highest and best use** of the lot is often a new luxury build, not the existing house.
- Developers will pay for **land value + build opportunity**, not for the old structure.
- Sellers are happy because they get more than the portal estimate; you are happy because the developer pays an assignment fee for the packaged deal.

### Example from the Video

| Metric | Value |
|--------|-------|
| Zillow estimate | $956,000 |
| Contract price | $1,880,000 |
| Assignment price | $1,950,000 |
| Spread | ~$70,000 assignment fee |
| End buyer | Developer tearing down and building new |
| Neighbor lot new-build exit | $9,300,000 |

Another example: a property listed at $8.5M on 3/4 acre; the developer bought the original lot for $1.4M in 2024. Surrounding Zillow estimates were ~$1M for similar old homes. The gap is the opportunity.

## How to Find These Deals

1. **Identify neighborhoods with active luxury new construction** ($3M–$9M+ new builds).
2. **Find older homes on comparable lots** in the same micro-neighborhood.
3. **Compare Zillow estimate vs. new-build land cost / sale price.**
4. **If land value >> structure estimate, the property is a candidate.**
5. **Contact the owner with an offer above Zestimate** (but below developer land budget).
6. **Assign the contract to a developer** who has the capital and appetite to build.

## Reverse Engineering: Locating These Neighborhoods in Florida

### Florida Market Context (Backed by Recent Data)

- **Florida leads the U.S. in residential teardown permits.** In 2025 Florida accounted for **14.6% of all U.S. demolition permits**, ahead of California (13.3%), New Jersey (10.4%), Texas (7.2%), and New York (4.1%).
- **Teardowns accounted for ~7% of single-family housing starts nationally in 2024.**
- **South Florida ultra-luxury sales are near record highs:** 361 closings at $10M+ in 2025; projected to end the year around 426.
- **Top Florida ultra-luxury markets:** Naples, Miami Beach, Palm Beach, Manalapan, West Palm Beach, Fort Lauderdale.
- **Naples beachfront estate sold for $133M in April 2025** — most expensive U.S. residential transaction that year.
- **Manalapan teardown asking $33M went under contract in July 2025** (1200 South Ocean Boulevard), marketed as teardown/renovation.
- **Winter Park, FL** is explicitly described as a lot-by-lot redevelopment market: older homes on valuable land replaced by custom luxury residences.

### What to Look For

| Filter | Rationale |
|--------|-----------|
| Lot size above local norm | >0.5 acres in coastal/estate areas; >0.25 acres in dense infill |
| Older homes | Pre-1990, ideally pre-1970 — more likely functionally obsolete |
| Proximity to new luxury builds | Within 0.5 mile of $3M+ new construction sales/listings |
| Waterfront / water view / golf course | Drives highest land premiums |
| Zillow gap | Zestimate is materially below recent land-only or new-build land cost |
| Buildable under current zoning | No environmental/legal barrier to demolition/rebuild |

### Prime Florida Counties / Cities to Screen

**South Florida (established luxury teardown activity)**
- Miami-Dade: Miami Beach, Coral Gables, Pinecrest, Key Biscayne
- Broward: Fort Lauderdale, Las Olas, Harbor Beach
- Palm Beach: Palm Beach, West Palm Beach, Manalapan, Delray Beach, Boca Raton

**Gulf Coast**
- Collier: Naples (Port Royal, Old Naples, Moorings, Park Shore)
- Sarasota: Sarasota, Siesta Key, Longboat Key
- Lee: Fort Myers Beach, Cape Coral (lower price tier but active)

**Central Florida**
- Orange: Winter Park, Windermere, Lake Nona (lot-by-lot redevelopment)

**Atlantic Coast**
- Indian River: Vero Beach
- St. Johns: Ponte Vedra Beach
- Duval: Jacksonville (San Marco, Riverside, Ortega)

## Data Sources to Back the Decision

### Free / Public

| Source | What It Gives |
|--------|---------------|
| **Zillow / Redfin** | Zestimates, recent sales, new construction listings, price history, lot size, year built |
| **Realtor.com** | New construction inventory, median list prices, days on market |
| **County Property Appraiser** | Sales history, assessed land/building values, ownership, lot dimensions, year built |
| **County GIS / Parcel Maps** | Lot shape, flood zone, zoning, surrounding land use |
| **City/County Building Permits** | Demolition permits, new residential construction permits, permit values |
| **Google Maps / Street View** | Visual confirmation of old home next to new builds |
| **Census / ACS** | Household income, population growth, migration inflow |
| **IRS Migration Data** | High-earning household inflow (Florida #1 net gain) |

### Paid / Professional

| Source | What It Gives |
|--------|---------------|
| **Propwire** | Owner lists, MLS days-on-market, out-of-state filters, skip trace |
| **CoStar / Reonomy / LandVision** | Commercial-grade ownership, zoning, sales, development pipeline |
| **ATTOM Data Solutions** | Property, mortgage, foreclosure, and sales data |
| **CoreLogic** | MLS data, valuations, market trends |
| **Construction Monitor / BuildZoom** | Permit data with dollar values and contractor info |
| **Local MLS access** | Off-market and pre-market opportunities |

### Smart Screen Logic

A neighborhood qualifies if:
1. New construction single-family homes closed at **$3M+** in the last 12 months within a 1-mile radius.
2. Existing homes on comparable lots have **Zestimates or list prices at least 40–60% below** the new-build sale price per square foot (adjusted for lot size).
3. **Demolition + new-build permits** are trending up in the ZIP code.
4. **Lot size and zoning** support a teardown/rebuild (not historic district, not multi-family restricted).
5. **Days on market** for older inventory is rising — sellers may be more receptive.

## Outreach Positioning

- Lead with: **"I can pay more than your Zillow estimate because I'm working with developers who want the lot, not the house."**
- Anchor low cash offer, then offer **more with seller financing** if needed.
- Typical seller-finance terms from related methods: 10% down, 4–5% interest, 5-year term.
- Always reassure the seller's agent: they can represent you and earn the full commission.
- For stale luxury listings, ask the listing agent: **"How negotiable is the seller? I can pay more with seller financing. Do you have any other properties?"**

## Key Metrics to Track

- **Target assignment fee:** $50k–$150k+ per deal.
- **Offer vs. Zestimate:** 100–200% of Zestimate can still work if land value supports it.
- **Developer land budget:** roughly 25–35% of expected new-build sale price.
- **Permit velocity:** demo + new-build permits per ZIP per quarter.
- **Spread needed:** contract price + assignment fee < developer's land budget.

## Relationship to the Dashboard

This is a **highest-and-best-use** play, not a raw-land play. Use the same lead sources as the Sourcing tab (Propwire, Redfin, MLS, skip tracing), but with different filters:

- **Property type:** Single-family (not vacant land).
- **Year built:** Pre-1990, ideally pre-1970.
- **Lot size:** Top quartile in ZIP or >0.25 acres in dense areas, >0.5 acres in coastal/estate areas.
- **Value gap:** Zestimate or assessed value significantly below new-build land cost.
- **Days on market:** >90 days, price reduced, "motivated" in description.
- **Location:** Within 0.5–1 mile of recent $3M+ new construction closings.

The marketing message is the opposite of traditional wholesaling: **"I will pay you MORE than Zillow says it's worth."**
