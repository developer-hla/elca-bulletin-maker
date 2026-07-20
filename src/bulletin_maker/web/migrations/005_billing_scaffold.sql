-- Billing scaffold: somewhere to record the payment-provider customer id.
-- Stripe-shaped only — no Stripe SDK, no payment endpoints, no plan changes.
-- A real billing workstream wires this up later. See docs/plans.md.

ALTER TABLE churches ADD COLUMN billing_customer_id text;
