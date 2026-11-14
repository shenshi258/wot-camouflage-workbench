import unittest
from unittest.mock import Mock,patch
from client_probe import verify


class ClientProbeTests(unittest.TestCase):
    def test_matching_interfaces_do_not_claim_game_test(self):
        p=Mock(varnames=(b'self',b'vID',b'vInfo',b'renderMode'),argcount=4,
               names=(b'_CommonTankAppearance__typeDesc',b'_prepareOutfit',b'typeDescriptor'))
        outfit=Mock(varnames=(b'self',b'outfitCD'),argcount=2)
        with patch('client_probe._methods',side_effect=[{b'prerequisites':p,b'_prepareOutfit':outfit},{b'_prepareOutfit':outfit}]):
            result=verify(Mock(read=Mock(return_value=b'bytes')))
        self.assertEqual(result['status'],'static_match_only')

    def test_unrecognized_client_is_rejected(self):
        p=Mock(varnames=(b'self',b'oldArgument'),argcount=2,names=())
        outfit=Mock(varnames=(b'self',b'outfitCD'),argcount=2)
        with patch('client_probe._methods',side_effect=[{b'prerequisites':p,b'_prepareOutfit':outfit},{b'_prepareOutfit':outfit}]):
            with self.assertRaises(ValueError):verify(Mock(read=Mock(return_value=b'bytes')))

    def test_dual_mode_checks_nested_descriptor_layout(self):
        p=Mock(varnames=(b'self',b'vID',b'vInfo',b'renderMode'),argcount=4,
               names=(b'_CommonTankAppearance__typeDesc',b'_prepareOutfit',b'typeDescriptor'))
        outfit=Mock(varnames=(b'self',b'outfitCD'),argcount=2)
        inner=(b'_CompositeVehicleDescriptor__vehicleDescr',b'_CompositeVehicleDescriptor__siegeDescr')
        part=Mock(names=inner)
        methods=[{b'prerequisites':p,b'_prepareOutfit':outfit},{b'_prepareOutfit':outfit},
                 {b'__init__':part,b'__getattr__':part,b'__setattr__':part}]
        with patch('client_probe._methods',side_effect=methods):
            result=verify(Mock(read=Mock(return_value=b'bytes')),require_composite=True)
        self.assertIn('composite_sha256',result)
        part.names=(b'_CompositeVehicleDescriptor__vehicleDescr',)
        with patch('client_probe._methods',side_effect=methods):
            with self.assertRaises(ValueError):verify(Mock(read=Mock(return_value=b'bytes')),require_composite=True)
