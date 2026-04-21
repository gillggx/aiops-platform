"""Long-lived background tasks: event poller + NATS subscriber.

Phase 5c: wiring + lifecycle. The actual tail/subscribe loops are stubs with
the publish path already threaded through ``JavaAPIClient.create_generated_event``,
so turning on a real MongoDB / NATS source is a one-liner change per module.
"""
