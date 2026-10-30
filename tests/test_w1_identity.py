"""Frozen source and raw gate receipts cannot silently drift between cards."""
import hashlib,json,tempfile,unittest
from pathlib import Path


class FrozenIdentity(unittest.TestCase):
    def test_failed_gate_and_tampered_raw_log_are_rejected(self):
        from bench.w1.identity import verify_gate
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            freeze=root/"freeze.json";freeze.write_text("{}")
            log=root/"synthetic-gate.log";log.write_text("Synthetic gate fixture only")
            gate=root/"gate.json"
            data={"exit_code":1,"full_gate":True,"lock_mode":"SH","argv":["scripts/check"],
                "source_freeze_sha256":hashlib.sha256(freeze.read_bytes()).hexdigest(),"raw_log":str(log),
                "raw_log_sha256":hashlib.sha256(log.read_bytes()).hexdigest()}
            gate.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"gate0"): verify_gate(gate,freeze)
            data["exit_code"]=0;gate.write_text(json.dumps(data))
            self.assertEqual(verify_gate(gate,freeze)["exit_code"],0)
            log.write_text("changed")
            with self.assertRaisesRegex(ValueError,"raw log changed"): verify_gate(gate,freeze)

    def test_changed_source_inventory_requires_a_new_freeze(self):
        from bench.w1.identity import freeze,verify_freeze
        probe=Path("bench/w1/.identity-probe.py")
        self.assertFalse(probe.exists())
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/"freeze.json"
            freeze(target)
            self.assertEqual(verify_freeze(target)["schema_version"],1)
            try:
                probe.write_text("probe=True\n")
                with self.assertRaisesRegex(ValueError,"freeze differs"): verify_freeze(target)
            finally: probe.unlink()
            self.assertEqual(verify_freeze(target)["schema_version"],1)
