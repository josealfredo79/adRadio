"""
Laboratorio — the bot tests itself before it talks to real customers.

Six simulated personas hold a full conversation against the REAL bot
pipeline (answer_with_rag), entirely in a sandbox: nothing here ever
imports or calls a WhatsApp send function (meta_service/twilio_service).
An independent LLM judge then scores each conversation and reports
findings. See personas.py, simulator.py, judge.py, runner.py.
"""
