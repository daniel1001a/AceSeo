// lib/seo/structured-data.ts
// Schema.org JSON-LD for BoardFlight.
//
// WHY THIS FILE EXISTS AT ALL, given the pages already carry good <title>/<meta>: a brand-new
// domain has no link graph and no brand recognition, so the only thing a crawler can go on is
// how legible the page makes itself. Structured data is the one part of that we control
// outright — it names the publisher, ties the airport pages into a browsable hierarchy, and
// states in machine-readable form what the FAQ answers are.
//
// THE RULE FOR EVERYTHING BELOW: JSON-LD must describe what the page actually says. Structured
// data that overstates — an aggregateRating with no reviews, a Dataset we don't publish, an
// Organization with fabricated founding details — is both a Google spam violation and exactly
// the kind of confidence-outrunning-accuracy this product refuses to do in its UI. Every field
// here is derivable from something a visitor can read on the page.
//
// (Deliberately NOT included: `aggregateRating` and `review` — we have no reviews. `Dataset` —
// we don't publish a downloadable dataset. `Product`/`Offer` — nothing is sold.)

import { allAirports, baseUrl, type AirportRow } from "./airports";
import { CONTACT_EMAIL } from "./brand";

/** The publisher node. Referenced by @id from every other node so it is stated once. */
export function organizationLd() {
  const base = baseUrl();
  return {
    "@type": "Organization",
    "@id": `${base}/#organization`,
    name: "BoardFlight",
    url: base,
    // A RASTER, with its dimensions stated. Google's logo guidance is written against pixels —
    // the image has to be crawlable, indexable, and at least 112x112 — and an SVG has no
    // intrinsic size to check that against, so a vector logo is the kind of field a crawler is
    // free to quietly drop. app/apple-icon.png is 180x180 and is the same tile artwork
    // scripts/build-icons.ts writes from public/brand/icon-tile.svg, so it cannot drift from the
    // favicon. (It carries square corners rather than the tile's rx=21 — that is deliberate, iOS
    // applies its own squircle; at logo scale in a search result it is not a visible difference,
    // and it is not worth a second committed raster to remove.)
    logo: {
      "@type": "ImageObject",
      url: `${base}/apple-icon.png`,
      width: 180,
      height: 180,
    },
    description:
      "BoardFlight computes the time to arrive at the airport for a specific flight, modeling each step from the curb to the departure gate.",
    // Emitted only when a mailbox actually exists. A contactPoint is a claim that someone answers
    // there, and the /contact page is built from the same constant — so the markup and the page
    // can never disagree about whether the site has a contact route.
    ...(CONTACT_EMAIL
      ? {
          contactPoint: {
            "@type": "ContactPoint",
            contactType: "customer support",
            email: CONTACT_EMAIL,
            url: `${base}/contact`,
            availableLanguage: "English",
          },
        }
      : {}),
  };
}

/**
 * The /contact page node. `ContactPage` is the schema.org type for exactly this, and stating it
 * is how a crawler tells a real contact route from any other page that happens to list an
 * address — one of the signals behind a brand's contact link in search results.
 */
export function contactPageLd() {
  const base = baseUrl();
  return {
    "@type": "ContactPage",
    "@id": `${base}/contact#page`,
    url: `${base}/contact`,
    name: "Contact BoardFlight",
    isPartOf: { "@id": `${base}/#website` },
    about: { "@id": `${base}/#organization` },
  };
}

/** The site node — lets a crawler treat the whole domain as one property. */
export function webSiteLd() {
  const base = baseUrl();
  return {
    "@type": "WebSite",
    "@id": `${base}/#website`,
    url: base,
    name: "BoardFlight",
    publisher: { "@id": `${base}/#organization` },
    inLanguage: "en-US",
  };
}

/**
 * The product itself. `WebApplication` rather than `SoftwareApplication` because it runs in the
 * browser with nothing to install. `price: "0"` is a fact, not a marketing claim — the FAQ says
 * the same thing, and stating it is what makes the free-to-use answer machine-readable.
 */
export function webApplicationLd() {
  const base = baseUrl();
  return {
    "@type": "WebApplication",
    "@id": `${base}/#app`,
    name: "BoardFlight",
    url: base,
    applicationCategory: "TravelApplication",
    operatingSystem: "Any",
    browserRequirements: "Requires JavaScript.",
    publisher: { "@id": `${base}/#organization` },
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
    },
    featureList: [
      "Arrive-by time computed for a specific flight number and departure",
      "Terminal-level security and walking-time modeling at 33 US airports",
      "Hour-by-hour view of when security is busiest",
      "PreCheck, CLEAR, checked-bag and international adjustments",
      "Calendar export with a leave-now reminder",
    ],
  };
}

/**
 * Trail for the airport pages: Home → Airports → this airport. Worth the bytes because these
 * pages are the free-traffic wedge; a crawler that understands the hierarchy is likelier to
 * treat /airports as a hub rather than 33 unrelated leaves.
 */
export function breadcrumbLd(trail: { name: string; path: string }[]) {
  const base = baseUrl();
  return {
    "@type": "BreadcrumbList",
    itemListElement: trail.map((step, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: step.name,
      item: `${base}${step.path}`,
    })),
  };
}

/**
 * FAQ nodes. `answer` is plain text on purpose: it must be the SAME answer the visitor reads,
 * so the page copy is the single source and this is a projection of it — see
 * app/how-it-works/page.tsx, which builds both its rendered FAQ and this markup from one array.
 */
export function faqPageLd(items: { question: string; answer: string }[]) {
  return {
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };
}

/** The airports hub as a real, enumerated list rather than an undifferentiated page of links. */
export function airportListLd(airports: AirportRow[] = allAirports()) {
  const base = baseUrl();
  return {
    "@type": "ItemList",
    name: "US airports profiled by BoardFlight",
    numberOfItems: airports.length,
    itemListElement: airports.map((a, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: `${a.meta.name} (${a.code})`,
      url: `${base}/airport/${a.code.toLowerCase()}`,
    })),
  };
}

/**
 * The airport a page is about, as a real place. `Airport` is a schema.org type in its own right
 * (Place → CivicStructure → Airport), so this is the honest description of the subject — not a
 * stretch of a generic type. iataCode is the one identifier we can state with certainty.
 */
export function airportLd(airport: AirportRow) {
  return {
    "@type": "Airport",
    name: airport.meta.name,
    iataCode: airport.code,
    ...(airport.meta.city ? { address: { "@type": "PostalAddress", addressLocality: airport.meta.city, addressCountry: "US" } } : {}),
  };
}

/**
 * Wrap a set of nodes into one `@graph` document and serialize it for a <script> tag.
 *
 * One graph per page rather than several sibling <script> blocks: it lets the nodes reference
 * each other by @id (every page points at the same #organization) instead of each restating the
 * publisher, which is both smaller and impossible to let drift.
 *
 * The `<` escape is not decoration. JSON-LD sits inside a raw <script> element, where the HTML
 * parser is looking for the literal string "</script" — an airport name or FAQ answer that ever
 * contained one would end the script early and dump markup into the page. Escaping the angle
 * bracket to its unicode form keeps the JSON identical to a parser and inert to the tokenizer.
 */
export function jsonLd(...nodes: object[]): string {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@graph": nodes,
  }).replace(/</g, "\\u003c");
}
