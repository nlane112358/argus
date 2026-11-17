#!/usr/bin/env python3
"""
Generates the official EU Law & EUDR Jurisdiction GeoJSON dataset for Argus.
Includes:
- All 27 European Union Member States (direct statutory jurisdiction under Regulation (EU) 2023/1115 & EU Treaties)
- European Economic Area (EEA) / EFTA Partners (Single Market alignment)
- Key EUDR Regulated Commodity Origin / Sourcing Producer Countries (Art. 3 & Art. 9 due diligence mandates)
"""

import json
import os
import sys
from osgeo import ogr

def generate_eu_law_dataset(input_world_path="/tmp/world_countries.geojson", output_geojson="static/eu_law_areas.geojson", output_js="static/eu_law_areas.js"):
    if not os.path.exists(input_world_path):
        print(f"Error: input world countries file {input_world_path} not found.")
        sys.exit(1)

    with open(input_world_path) as f:
        world_data = json.load(f)

    eu_members = {
        'Austria': {'code': 'AT', 'commodities': ['Wood', 'Cattle']},
        'Belgium': {'code': 'BE', 'commodities': ['Wood', 'Cattle']},
        'Bulgaria': {'code': 'BG', 'commodities': ['Wood', 'Cattle', 'Soy']},
        'Croatia': {'code': 'HR', 'commodities': ['Wood', 'Cattle']},
        'Cyprus': {'code': 'CY', 'commodities': ['Cattle']},
        'Czech Republic': {'code': 'CZ', 'commodities': ['Wood', 'Cattle', 'Soy'], 'display_name': 'Czechia'},
        'Czechia': {'code': 'CZ', 'commodities': ['Wood', 'Cattle', 'Soy']},
        'Denmark': {'code': 'DK', 'commodities': ['Cattle', 'Wood']},
        'Estonia': {'code': 'EE', 'commodities': ['Wood']},
        'Finland': {'code': 'FI', 'commodities': ['Wood', 'Cattle']},
        'France': {'code': 'FR', 'commodities': ['Wood', 'Cattle', 'Soy']},
        'Germany': {'code': 'DE', 'commodities': ['Wood', 'Cattle', 'Soy']},
        'Greece': {'code': 'GR', 'commodities': ['Cattle', 'Wood']},
        'Hungary': {'code': 'HU', 'commodities': ['Wood', 'Soy', 'Cattle']},
        'Ireland': {'code': 'IE', 'commodities': ['Cattle', 'Wood']},
        'Italy': {'code': 'IT', 'commodities': ['Wood', 'Cattle', 'Soy']},
        'Latvia': {'code': 'LV', 'commodities': ['Wood']},
        'Lithuania': {'code': 'LT', 'commodities': ['Wood']},
        'Luxembourg': {'code': 'LU', 'commodities': ['Wood', 'Cattle']},
        'Malta': {'code': 'MT', 'commodities': ['Cattle']},
        'Netherlands': {'code': 'NL', 'commodities': ['Cattle', 'Soy', 'Wood']},
        'Poland': {'code': 'PL', 'commodities': ['Wood', 'Cattle', 'Soy']},
        'Portugal': {'code': 'PT', 'commodities': ['Wood', 'Cattle']},
        'Romania': {'code': 'RO', 'commodities': ['Wood', 'Soy', 'Cattle']},
        'Slovakia': {'code': 'SK', 'commodities': ['Wood', 'Cattle', 'Soy']},
        'Slovenia': {'code': 'SI', 'commodities': ['Wood', 'Cattle']},
        'Spain': {'code': 'ES', 'commodities': ['Wood', 'Cattle', 'Soy']},
        'Sweden': {'code': 'SE', 'commodities': ['Wood', 'Cattle']}
    }

    eea_partners = {
        'Norway': {'code': 'NO', 'commodities': ['Wood']},
        'Iceland': {'code': 'IS', 'commodities': ['Cattle']},
        'Liechtenstein': {'code': 'LI', 'commodities': ['Wood']}
    }

    regulated_producers = {
        'Brazil': {'code': 'BR', 'commodities': ['Soy', 'Cattle', 'Coffee', 'Wood'], 'risk': 'Standard Risk (Art. 29)'},
        'Colombia': {'code': 'CO', 'commodities': ['Coffee', 'Palm Oil', 'Cocoa'], 'risk': 'Standard Risk (Art. 29)'},
        'Indonesia': {'code': 'ID', 'commodities': ['Palm Oil', 'Rubber', 'Wood', 'Coffee'], 'risk': 'Standard Risk (Art. 29)'},
        'Ivory Coast': {'code': 'CI', 'commodities': ['Cocoa', 'Coffee', 'Rubber'], 'display_name': "Côte d'Ivoire", 'risk': 'Standard Risk (Art. 29)'},
        "Côte d'Ivoire": {'code': 'CI', 'commodities': ['Cocoa', 'Coffee', 'Rubber'], 'risk': 'Standard Risk (Art. 29)'},
        'Peru': {'code': 'PE', 'commodities': ['Coffee', 'Cocoa', 'Palm Oil'], 'risk': 'Standard Risk (Art. 29)'},
        'Ghana': {'code': 'GH', 'commodities': ['Cocoa', 'Palm Oil'], 'risk': 'Standard Risk (Art. 29)'},
        'Malaysia': {'code': 'MY', 'commodities': ['Palm Oil', 'Rubber', 'Wood'], 'risk': 'Standard Risk (Art. 29)'},
        'Vietnam': {'code': 'VN', 'commodities': ['Coffee', 'Rubber', 'Wood'], 'risk': 'Standard Risk (Art. 29)'},
        'Cameroon': {'code': 'CM', 'commodities': ['Cocoa', 'Wood', 'Rubber'], 'risk': 'Standard Risk (Art. 29)'},
        'Argentina': {'code': 'AR', 'commodities': ['Soy', 'Cattle'], 'risk': 'Standard Risk (Art. 29)'}
    }

    features = []
    seen_names = set()

    for feat in world_data['features']:
        name = feat['properties'].get('name', '')
        if name in seen_names:
            continue

        if name in eu_members:
            seen_names.add(name)
            cfg = eu_members[name]
            dname = cfg.get('display_name', name)
            props = {
                'name': dname,
                'iso2': cfg.get('code') or feat['properties'].get('ISO3166-1-Alpha-2', ''),
                'iso3': feat['properties'].get('ISO3166-1-Alpha-3', ''),
                'jurisdiction_type': 'EU_MEMBER_STATE',
                'jurisdiction_label': 'EU Member State (Direct Statutory EU Law)',
                'legal_basis': 'Treaty on European Union & Regulation (EU) 2023/1115 (EUDR)',
                'market_status': 'EU Single Market Statutory Territory',
                'regulatory_mandate': 'Full direct statutory application. Competent Authorities execute due diligence audits (Art. 14-19), customs interception, and TRACES NT verification.',
                'operator_obligation': 'Domestic EU forestry & agricultural operators must submit Due Diligence Statements (DDS) to EU TRACES NT before placing relevant commodities on single market or exporting.',
                'risk_benchmarking': 'Standard Risk (Article 29 EUDR)',
                'relevant_commodities': cfg['commodities'],
                'fill_color': '#1E40AF',
                'border_color': '#F59E0B'
            }
        elif name in eea_partners:
            seen_names.add(name)
            cfg = eea_partners[name]
            props = {
                'name': name,
                'iso2': cfg.get('code') or feat['properties'].get('ISO3166-1-Alpha-2', ''),
                'iso3': feat['properties'].get('ISO3166-1-Alpha-3', ''),
                'jurisdiction_type': 'EEA_EFTA_PARTNER',
                'jurisdiction_label': 'European Single Market / EEA Partner',
                'legal_basis': 'EEA Agreement & EU Single Market Environmental Alignment',
                'market_status': 'European Single Market Integrated',
                'regulatory_mandate': 'Regulatory alignment with EU environmental and trade due diligence standards.',
                'operator_obligation': 'Harmonized operator due diligence and cross-border trade attestation.',
                'risk_benchmarking': 'Low / Standard Risk',
                'relevant_commodities': cfg['commodities'],
                'fill_color': '#0284C7',
                'border_color': '#38BDF8'
            }
        elif name in regulated_producers:
            seen_names.add(name)
            cfg = regulated_producers[name]
            dname = cfg.get('display_name', name)
            props = {
                'name': dname,
                'iso2': cfg.get('code') or feat['properties'].get('ISO3166-1-Alpha-2', ''),
                'iso3': feat['properties'].get('ISO3166-1-Alpha-3', ''),
                'jurisdiction_type': 'EUDR_REGULATED_PRODUCER',
                'jurisdiction_label': 'EUDR Regulated Sourcing Area (Third-Country Origin)',
                'legal_basis': 'Regulation (EU) 2023/1115 (EUDR) Article 3 & Article 9',
                'market_status': 'Regulated Supply Chain Origin for EU Market Entry',
                'regulatory_mandate': 'Mandatory statutory due diligence: commodities entering the EU single market must prove zero deforestation after 31 December 2020 cutoff.',
                'operator_obligation': 'EU importers and domestic suppliers must obtain polygon geolocation, verify zero canopy loss via bi-temporal satellite audit, and register Due Diligence Statements.',
                'risk_benchmarking': cfg.get('risk', 'Standard Risk (Art. 29)'),
                'relevant_commodities': cfg['commodities'],
                'fill_color': '#D97706',
                'border_color': '#FBBF24'
            }
        else:
            continue

        g = ogr.CreateGeometryFromJson(json.dumps(feat['geometry']))
        if not g:
            continue
        simp = g.SimplifyPreserveTopology(0.06)
        if not simp or simp.IsEmpty():
            simp = g
        sj = json.loads(simp.ExportToJson())

        def round_coords(val):
            if isinstance(val, (int, float)):
                return round(val, 4)
            return [round_coords(v) for v in val]
        sj['coordinates'] = round_coords(sj['coordinates'])

        features.append({
            'type': 'Feature',
            'properties': props,
            'geometry': sj
        })

    geojson_obj = {
        'type': 'FeatureCollection',
        'metadata': {
            'title': 'EU Law Territorial Application & EUDR Regulated Scope',
            'regulation': 'Regulation (EU) 2023/1115 (EUDR) & EU Treaties',
            'generated_for': 'Argus Satellite ESG & EUDR Auditor',
            'total_jurisdictions': len(features)
        },
        'features': features
    }

    os.makedirs(os.path.dirname(output_geojson), exist_ok=True)
    with open(output_geojson, 'w') as out_f:
        json.dump(geojson_obj, out_f, separators=(',', ':'))

    with open(output_js, 'w') as out_js:
        out_js.write('window.EU_LAW_AREAS = ' + json.dumps(geojson_obj, separators=(',', ':')) + ';\n')

    print(f"[+] Successfully exported {len(features)} jurisdictions to {output_geojson} and {output_js}")

if __name__ == '__main__':
    generate_eu_law_dataset()
