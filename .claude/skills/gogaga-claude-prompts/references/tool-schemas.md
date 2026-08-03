# Tool Schemas v0.1 (Anthropic tools format — keep in sync with code)

extract_lead_details — call immediately when ANY field is learned; partial ok
  input: {destination?: string, travel_dates?: string, pax_count?: int, budget_inr?: int, duration_days?: int}
  → server merges into travel_leads (never overwrite non-null with null)

get_packages — the ONLY source of offerable packages
  input: {destination: string, budget_inr?: int}
  → returns [{name, price_inr, duration_days, highlights}] from travel_packages

request_human_handoff
  input: {reason: enum[customer_request, frustration, high_value, out_of_scope]}
  → flags call for takeover (P3 wires the conference)

schedule_followup
  input: {day_offset: enum[1,3,7], note: string}
  → creates ladder entry (P4 wires sending via playbooks)

# CHANGELOG
- v0.1 starter schemas pre-Phase 2. Update alongside prompts.py.
