"""Source-only contextual blockers: synthetic generalizations plus failure reproductions.

These patterns were designed after seeing the Pilot-120 misses, so tests are
engineering checks only. They are not clean holdout generalization tests.
"""
import unittest
from compound_manager.source_probe_v03 import probe, PROBE_VERSION


def src(command, scene, dialogue=()):
    return {"record_id":"synthetic", "command":command,
            "scene_context":scene, "dialogue_history":list(dialogue)}


class ContextualReadinessTests(unittest.TestCase):
    def assert_blocked(self, source, reason, target):
        out=probe(source)
        self.assertEqual(out['predicted_readiness'],'blocking_ambiguity')
        hits=[e for e in out['evidence'] if e['reason']==reason]
        self.assertEqual(len(hits), 1, (reason, out['evidence']))
        self.assertEqual(hits[0]['target'],target)
        self.assertIn(hits[0]['quote'].lower(), source['scene_context'].lower())
        self.assertTrue(hits[0]['question'])
        self.assertGreaterEqual(len(hits[0]['candidates']),2)
        self.assertFalse(out['candidate_coverage_verified'])
        return hits[0]

    def test_selected_tray_with_two_pending_assignments(self):
        scene=('Two serving trays are selected and both remain pending. '
               'The grey one is assigned to chef; the amber one is assigned to guest. '
               'The command provides no item code, color, or recipient name. '
               'Both pending assignments are pre-authorized handoffs.')
        hit=self.assert_blocked(src('Deliver the selected serving tray using the usual setup.',scene),
                                'two_pending_selected_objects','selected_item')
        self.assertEqual(len(hit['candidates']),2)
        self.assertTrue(any('grey' in x for x in hit['candidates']))

    def test_selected_guest_parcel(self):
        scene=('Two guest parcels are selected and both remain pending. '
               'The green one is assigned to floor supervisor; the blue one is assigned to porter. '
               'The command provides no item code, color, or recipient name.')
        self.assert_blocked(src('After the pickup, deliver the selected guest parcel.',scene),
                            'two_pending_selected_objects','selected_item')

    def test_handover_to_ambiguous_role(self):
        scene=('The handoff roster lists two recipients under the role homeowner: '
               'badge BLACK-17 at the console table and badge YELLOW-42 at the patio door. '
               'The delivery note contains only the role title. '
               'Recipient identity is required before handoff.')
        hit=self.assert_blocked(src('Deliver the blanket to the homeowner after arrival.',scene),
                                'nonunique_recipient_role','recipient_identity')
        self.assertIn('badge BLACK-17',hit['candidates'])
        self.assertIn('badge YELLOW-42',hit['candidates'])

    def test_two_secure_bays_and_no_work_order_unit(self):
        scene=('Two secure equipment bays are empty and authorized: unit A at the bay entrance '
               'and unit B at the handover board. The work order names neither unit. '
               'Secure-storage policy requires the unit identifier before placement.')
        hit=self.assert_blocked(src('Move the linen cart and the transfer cart, then return it to the secure equipment bay.',scene),
                                'unnamed_destination_unit','destination_unit')
        self.assertEqual(len(hit['candidates']),2)

    def test_two_archive_cages_with_no_selection(self):
        scene=('Two archive cages are authorized and empty, one at the catalogue terminal and one at the display corner. '
               'The work order names neither unit. Secure placement requires the unit identifier.')
        self.assert_blocked(src('Place it in the archive cage using the usual setup.',scene),
                            'unnamed_destination_unit','destination_unit')

    def test_two_shipping_cages_with_no_selection(self):
        scene=('Two secure cages are authorized and empty, one at the forklift lane and one at the inspection cage. '
               'The work order names neither unit. Secure placement requires the unit identifier.')
        self.assert_blocked(src('Do the same with the second shipping case, then place it in the secure cage.',scene),
                            'unnamed_destination_unit','destination_unit')

    def test_two_barrier_bays_without_unit(self):
        scene=('Two barrier storage bays are empty and authorized: unit A at the platform screen '
               'and unit B at the information desk. The work order names neither unit. '
               'Secure-storage policy requires the unit identifier before placement.')
        self.assert_blocked(src('Move the queue barrier and transfer cart, then return it to the barrier storage bay.',scene),
                            'unnamed_destination_unit','destination_unit')

    def test_two_carton_cages_without_unit(self):
        scene=('Two secure cages are empty and authorized: unit A at the inspection cage and '
               'unit B at the bay marker. The work order names neither unit. '
               'Secure-storage policy requires the unit identifier before placement.')
        self.assert_blocked(src('Move the carton and transfer cart, then return it to the secure cage.',scene),
                            'unnamed_destination_unit','destination_unit')

    def test_expected_range_controls_pressure_gauge(self):
        scene=('Two pressure gauges are staged at the active work point and are in calibration. '
               'The handheld unit covers the low range; the cart-mounted unit covers the high range. '
               'The work order does not state the expected range. '
               'The measurement protocol requires the range-appropriate instrument.')
        self.assert_blocked(src("Measure the vacuum's suction pressure with the pressure gauge.",scene),
                            'unknown_instrument_range','expected_range')

    def test_expected_range_controls_voltage_meter(self):
        scene=('Two voltage meters are staged at the active work point and are in calibration. '
               'The handheld unit covers the low range; the cart-mounted unit covers the high range. '
               'The work order does not state the expected range. '
               'The measurement protocol requires the range-appropriate instrument.')
        self.assert_blocked(src("Measure the table-order terminal's supply voltage with the voltage meter.",scene),
                            'unknown_instrument_range','expected_range')

    def test_negative_two_carts_no_unresolved_storage_choice(self):
        scene=('Two secure cages are empty. Work order WO-92 selects unit B. '
               'The robot can put the item in unit B.')
        out=probe(src('Return the cart to the secure cage.',scene))
        self.assertEqual(out['predicted_readiness'],'ready_candidate')

    def test_negative_multiple_items_but_no_missing_identifier(self):
        scene=('Two serving trays are selected, both pending. '
               'The selected tray with tag BLUE-77 is assigned to guest, and command names BLUE-77.')
        out=probe(src('Deliver the selected tray BLUE-77.',scene))
        self.assertEqual(out['predicted_readiness'],'ready_candidate')

    def test_negative_two_meters_with_range_stated(self):
        scene=('Two voltage meters are staged at the work point. '
               'The handheld unit covers the low range; the cart-mounted unit covers the high range. '
               'The work order states the expected range is high.')
        out=probe(src('Measure the supply voltage with the voltage meter.',scene))
        self.assertEqual(out['predicted_readiness'],'ready_candidate')

    def test_no_case_id_or_label_dependency(self):
        a=src('Deliver the selected guest parcel.', 'Two guest parcels are selected and both remain pending. The command provides no item code.')
        b={**a, 'record_id':'CA-FAKE-999', 'terminal_strategy':'execute', 'gold':'execute'}
        self.assertEqual(probe(a)['predicted_readiness'],probe(b)['predicted_readiness'])
        self.assertEqual(probe(b)['probe_version'],PROBE_VERSION)

if __name__=='__main__':unittest.main()