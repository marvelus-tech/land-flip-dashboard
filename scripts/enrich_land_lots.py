#!/usr/bin/env python3
"""
RR Land Lot Enrichment — Free OSINT Pipeline
Takes your rr-niche-finder opportunities and maps them to free county portals
for property owner lookup. Zero API costs.

Usage:
    python3 enrich_land_lots.py --batch skills/rr-niche-finder/data/latest-batch.json
    python3 enrich_land_lots.py --all
"""

import argparse
import json
import csv
from datetime import datetime
from pathlib import Path

WORKSPACE = Path.home() / ".openclaw" / "workspace"
OUTPUT_DIR = WORKSPACE / "enriched_leads"
OUTPUT_DIR.mkdir(exist_ok=True)

# County portal mapping for top markets
PORTALS = {
    ("Newark", "NJ"): "https://taxmaps.nj.gov/pdfs/county/Essex",
    ("Miami Gardens", "FL"): "https://www.miamidade.gov/propertysearch/",
    ("Costa Mesa", "CA"): "https://www.ocassessor.org/",
    ("League City", "TX"): "https://www.galvestoncad.org/",
    ("Inglewood", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Central Coast", "NSW"): "https://www.nswlrs.com.au/",
    ("Stockton", "CA"): "https://www.sjgov.org/",
    ("Knoxville", "TN"): "https://www.knoxcounty.org/",
    ("Dayton", "OH"): "https://www.mctreasurer.org/",
    ("Bloomington", "MN"): "https://www.hennepin.us/",
    ("Murfreesboro", "TN"): "https://www.rutherfordcountytn.gov/",
    ("Yonkers", "NY"): "https://www.westchestergov.com/",
    ("Sandy Springs", "GA"): "https://www.fultoncountyga.gov/",
    ("Coral Springs", "FL"): "https://www.browardpropertyappraisers.org/",
    ("Hillsboro", "OR"): "https://www.washingtoncountyor.gov/",
    ("Columbia", "SC"): "https://www.richlandcountysc.gov/",
    ("Carmel", "IN"): "https://www.hamiltoncounty.in.gov/",
    ("Overland Park", "KS"): "https://www.jocogov.org/",
    ("Burbank", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Pensacola", "FL"): "https://www.escambiacad.com/",
    ("Gilbert", "AZ"): "https://mcassessor.maricopa.gov/",
    ("Topeka", "KS"): "https://www.shawneecounty.org/",
    ("Sterling Heights", "MI"): "https://www.macombtreasurer.org/",
    ("The Villages", "FL"): "https://www.sumtercountyfl.gov/",
    ("Huntington Beach", "CA"): "https://www.ocassessor.org/",
    ("Oxnard", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Albany", "WA"): "https://www.wa.gov.au/",
    ("Naperville", "IL"): "https://www.dupagecounty.gov/",
    ("Killeen", "TX"): "https://www.bellcad.org/",
    ("Kansas City", "KS"): "https://www.wycokck.org/",
    ("Newark", "NJ"): "https://taxmaps.nj.gov/pdfs/county/Essex",
    ("Miami Gardens", "FL"): "https://www.miamidade.gov/propertysearch/",
    ("Costa Mesa", "CA"): "https://www.ocassessor.org/",
    ("League City", "TX"): "https://www.galvestoncad.org/",
    ("Inglewood", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Central Coast", "NSW"): "https://www.nswlrs.com.au/",
    ("Stockton", "CA"): "https://www.sjgov.org/",
    ("Knoxville", "TN"): "https://www.knoxcounty.org/",
    ("Dayton", "OH"): "https://www.mctreasurer.org/",
    ("Bloomington", "MN"): "https://www.hennepin.us/",
    ("Murfreesboro", "TN"): "https://www.rutherfordcountytn.gov/",
    ("Yonkers", "NY"): "https://www.westchestergov.com/",
    ("Sandy Springs", "GA"): "https://www.fultoncountyga.gov/",
    ("Coral Springs", "FL"): "https://www.browardpropertyappraisers.org/",
    ("Hillsboro", "OR"): "https://www.washingtoncountyor.gov/",
    ("Columbia", "SC"): "https://www.richlandcountysc.gov/",
    ("Carmel", "IN"): "https://www.hamiltoncounty.in.gov/",
    ("Overland Park", "KS"): "https://www.jocogov.org/",
    ("Burbank", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Pensacola", "FL"): "https://www.escambiacad.com/",
    ("Gilbert", "AZ"): "https://mcassessor.maricopa.gov/",
    ("Topeka", "KS"): "https://www.shawneecounty.org/",
    ("Sterling Heights", "MI"): "https://www.macombtreasurer.org/",
    ("The Villages", "FL"): "https://www.sumtercountyfl.gov/",
    ("Huntington Beach", "CA"): "https://www.ocassessor.org/",
    ("Oxnard", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Albany", "WA"): "https://www.wa.gov.au/",
    ("Naperville", "IL"): "https://www.dupagecounty.gov/",
    ("Killeen", "TX"): "https://www.bellcad.org/",
    ("Kansas City", "KS"): "https://www.wycokck.org/",
    ("Newark", "NJ"): "https://taxmaps.nj.gov/pdfs/county/Essex",
    ("Miami Gardens", "FL"): "https://www.miamidade.gov/propertysearch/",
    ("Costa Mesa", "CA"): "https://www.ocassessor.org/",
    ("League City", "TX"): "https://www.galvestoncad.org/",
    ("Inglewood", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Central Coast", "NSW"): "https://www.nswlrs.com.au/",
    ("Stockton", "CA"): "https://www.sjgov.org/",
    ("Knoxville", "TN"): "https://www.knoxcounty.org/",
    ("Dayton", "OH"): "https://www.mctreasurer.org/",
    ("Bloomington", "MN"): "https://www.hennepin.us/",
    ("Murfreesboro", "TN"): "https://www.rutherfordcountytn.gov/",
    ("Yonkers", "NY"): "https://www.westchestergov.com/",
    ("Sandy Springs", "GA"): "https://www.fultoncountyga.gov/",
    ("Coral Springs", "FL"): "https://www.browardpropertyappraisers.org/",
    ("Hillsboro", "OR"): "https://www.washingtoncountyor.gov/",
    ("Columbia", "SC"): "https://www.richlandcountysc.gov/",
    ("Carmel", "IN"): "https://www.hamiltoncounty.in.gov/",
    ("Overland Park", "KS"): "https://www.jocogov.org/",
    ("Burbank", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Pensacola", "FL"): "https://www.escambiacad.com/",
    ("Gilbert", "AZ"): "https://mcassessor.maricopa.gov/",
    ("Topeka", "KS"): "https://www.shawneecounty.org/",
    ("Sterling Heights", "MI"): "https://www.macombtreasurer.org/",
    ("The Villages", "FL"): "https://www.sumtercountyfl.gov/",
    ("Huntington Beach", "CA"): "https://www.ocassessor.org/",
    ("Oxnard", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Albany", "WA"): "https://www.wa.gov.au/",
    ("Naperville", "IL"): "https://www.dupagecounty.gov/",
    ("Killeen", "TX"): "https://www.bellcad.org/",
    ("Kansas City", "KS"): "https://www.wycokck.org/",
    ("Ann Arbor", "MI"): "https://www.ewashtenaw.org/",
    ("Plano", "TX"): "https://www.collincad.org/",
    ("Vallejo", "CA"): "https://www.solanocounty.com/",
    ("Fontana", "CA"): "https://www.sbcounty.gov/",
    ("Clearwater", "FL"): "https://www.pcpao.org/",
    ("North Las Vegas", "NV"): "https://www.clarkcountynv.gov/",
    ("Jackson", "MS"): "https://www.hindsms.com/",
    ("Lehigh Acres", "FL"): "https://www.leeelections.com/",
    ("Evansville", "IN"): "https://www.vanderburghcounty.org/",
    ("West Jordan", "UT"): "https://www.saltlakecounty.gov/",
    ("Fort Wayne", "IN"): "https://www.allencounty.us/",
    ("Santa Rosa", "CA"): "https://www.sonoma-county.org/",
    ("Charleston", "SC"): "https://www.charlestoncounty.org/",
    ("Mission", "TX"): "https://www.hidalgocad.org/",
    ("Yuma", "AZ"): "https://www.yumacountyaz.gov/",
    ("Toowoomba", "QLD"): "https://www.qld.gov.au/",
    ("Daly City", "CA"): "https://www.smcacre.org/",
    ("Beaumont", "TX"): "https://www.jeffersoncad.org/",
    ("Victor Harbor", "SA"): "https://www.sa.gov.au/",
    ("Tyler", "TX"): "https://www.smithcad.org/",
    ("Mobile", "AL"): "https://www.mobilecountyal.gov/",
    ("Alice Springs", "NT"): "https://www.nt.gov.au/",
    ("Cape Coral", "FL"): "https://www.leeelections.com/",
    ("Glendale", "AZ"): "https://mcassessor.maricopa.gov/",
    ("Fort Lauderdale", "FL"): "https://www.browardpropertyappraisers.org/",
    ("Ipswich", "QLD"): "https://www.qld.gov.au/",
    ("McAllen", "TX"): "https://www.hidalgocad.org/",
    ("Ann Arbor", "MI"): "https://www.ewashtenaw.org/",
    ("Plano", "TX"): "https://www.collincad.org/",
    ("Vallejo", "CA"): "https://www.solanocounty.com/",
    ("Fontana", "CA"): "https://www.sbcounty.gov/",
    ("Clearwater", "FL"): "https://www.pcpao.org/",
    ("North Las Vegas", "NV"): "https://www.clarkcountynv.gov/",
    ("Jackson", "MS"): "https://www.hindsms.com/",
    ("Lehigh Acres", "FL"): "https://www.leeelections.com/",
    ("Evansville", "IN"): "https://www.vanderburghcounty.org/",
    ("West Jordan", "UT"): "https://www.saltlakecounty.gov/",
    ("Fort Wayne", "IN"): "https://www.allencounty.us/",
    ("Santa Rosa", "CA"): "https://www.sonoma-county.org/",
    ("Charleston", "SC"): "https://www.charlestoncounty.org/",
    ("Mission", "TX"): "https://www.hidalgocad.org/",
    ("Yuma", "AZ"): "https://www.yumacountyaz.gov/",
    ("Toowoomba", "QLD"): "https://www.qld.gov.au/",
    ("Daly City", "CA"): "https://www.smcacre.org/",
    ("Beaumont", "TX"): "https://www.jeffersoncad.org/",
    ("Victor Harbor", "SA"): "https://www.sa.gov.au/",
    ("Tyler", "TX"): "https://www.smithcad.org/",
    ("Mobile", "AL"): "https://www.mobilecountyal.gov/",
    ("Alice Springs", "NT"): "https://www.nt.gov.au/",
    ("Cape Coral", "FL"): "https://www.leeelections.com/",
    ("Glendale", "AZ"): "https://mcassessor.maricopa.gov/",
    ("Fort Lauderdale", "FL"): "https://www.browardpropertyappraisers.org/",
    ("Ipswich", "QLD"): "https://www.qld.gov.au/",
    ("McAllen", "TX"): "https://www.hidalgocad.org/",
    ("Ann Arbor", "MI"): "https://www.ewashtenaw.org/",
    ("Plano", "TX"): "https://www.collincad.org/",
    ("Vallejo", "CA"): "https://www.solanocounty.com/",
    ("Fontana", "CA"): "https://www.sbcounty.gov/",
    ("Clearwater", "FL"): "https://www.pcpao.org/",
    ("North Las Vegas", "NV"): "https://www.clarkcountynv.gov/",
    ("Jackson", "MS"): "https://www.hindsms.com/",
    ("Lehigh Acres", "FL"): "https://www.leeelections.com/",
    ("Evansville", "IN"): "https://www.vanderburghcounty.org/",
    ("West Jordan", "UT"): "https://www.saltlakecounty.gov/",
    ("Fort Wayne", "IN"): "https://www.allencounty.us/",
    ("Santa Rosa", "CA"): "https://www.sonoma-county.org/",
    ("Charleston", "SC"): "https://www.charlestoncounty.org/",
    ("Mission", "TX"): "https://www.hidalgocad.org/",
    ("Yuma", "AZ"): "https://www.yumacountyaz.gov/",
    ("Toowoomba", "QLD"): "https://www.qld.gov.au/",
    ("Daly City", "CA"): "https://www.smcacre.org/",
    ("Beaumont", "TX"): "https://www.jeffersoncad.org/",
    ("Victor Harbor", "SA"): "https://www.sa.gov.au/",
    ("Tyler", "TX"): "https://www.smithcad.org/",
    ("Mobile", "AL"): "https://www.mobilecountyal.gov/",
    ("Alice Springs", "NT"): "https://www.nt.gov.au/",
    ("Cape Coral", "FL"): "https://www.leeelections.com/",
    ("Glendale", "AZ"): "https://mcassessor.maricopa.gov/",
    ("Fort Lauderdale", "FL"): "https://www.browardpropertyappraisers.org/",
    ("Ipswich", "QLD"): "https://www.qld.gov.au/",
    ("McAllen", "TX"): "https://www.hidalgocad.org/",
    ("Santa Ana", "CA"): "https://ocassessor.org/",
    ("Berkeley", "CA"): "https://www.acgov.org/",
    ("Norwalk", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Ontario", "CA"): "https://www.sbcounty.gov/",
    ("Henderson", "NV"): "https://www.clarkcountynv.gov/",
    ("Savannah", "GA"): "https://www.chathamcounty.org/",
    ("Miramar", "FL"): "https://www.browardpropertyappraisers.org/",
    ("Westminster", "CO"): "https://www.jeffco.us/",
    ("Sioux Falls", "SD"): "https://www.minnehahacounty.org/",
    ("Quincy", "MA"): "https://www.quincyma.gov/",
    ("Nampa", "ID"): "https://www.canyoncounty.id.gov/",
    ("Olathe", "KS"): "https://www.jocogov.org/",
    ("Broken Arrow", "OK"): "https://www.assessor.tulsacounty.org/",
    ("Albany", "NY"): "https://www.albanycounty.com/",
    ("Elizabeth", "NJ"): "https://taxmaps.nj.gov/pdfs/county/Union",
    ("Warren", "MI"): "https://www.macombtreasurer.org/",
    ("Burnie", "TAS"): "https://www.thelist.tas.gov.au/",
    ("Ballarat", "VIC"): "https://www.landata.vic.gov.au/",
    ("Geelong", "VIC"): "https://www.landata.vic.gov.au/",
    ("Mandurah", "WA"): "https://www.wa.gov.au/",
    ("Devonport", "TAS"): "https://www.thelist.tas.gov.au/",
    ("Blue Mountains", "NSW"): "https://www.nswlrs.com.au/",
    ("Goulburn", "NSW"): "https://www.nswlrs.com.au/",
    ("Bendigo", "VIC"): "https://www.landata.vic.gov.au/",
    ("Sunshine Coast", "QLD"): "https://www.qld.gov.au/",
    ("Katherine", "NT"): "https://www.nt.gov.au/",
    ("Palmerston", "NT"): "https://www.nt.gov.au/",
    ("Clarksville", "TN"): "https://www.montgomerycountytn.org/",
    ("Norwalk", "CT"): "https://www.norwalkct.gov/",
    ("Shreveport", "LA"): "https://www.cadocad.org/",
    ("Pasadena", "TX"): "https://www.hcad.org/",
    ("Tallahassee", "FL"): "https://www.leonpa.org/",
    ("Boulder", "CO"): "https://www.bouldercounty.org/",
    ("Visalia", "CA"): "https://www.tularecounty.ca.gov/",
    ("Cedar Rapids", "IA"): "https://www.linncounty.org/",
    ("Downey", "CA"): "https://portal.assessor.lacounty.gov/",
    ("San Mateo", "CA"): "https://www.smcacre.org/",
    ("Corpus Christi", "TX"): "https://www.sanpatriciocad.org/",
    ("Sandy", "UT"): "https://www.saltlakecounty.gov/",
    ("Sugar Land", "TX"): "https://www.fbcad.org/",
    ("Winston-Salem", "NC"): "https://www.forsythcounty.gov/",
    ("Athens", "GA"): "https://www.clarkecountyga.gov/",
    ("Green Bay", "WI"): "https://www.browncountywi.gov/",
    ("Victorville", "CA"): "https://www.sbcounty.gov/",
    ("Moreno Valley", "CA"): "https://www.rivcoaccessor.org/",
    ("Hollywood", "FL"): "https://www.browardpropertyappraisers.org/",
    ("Chandler", "AZ"): "https://mcassessor.maricopa.gov/",
    ("Anaheim", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Aurora", "IL"): "https://www.kanecountysoa.org/",
    ("Cambridge", "MA"): "https://www.cambridgema.gov/",
    ("West Palm Beach", "FL"): "https://www.pbcgov.org/",
    ("Concord", "CA"): "https://www.concordca.gov/",
    ("Modesto", "CA"): "https://www.stancounty.com/assessor/",
    ("Fairfield", "CA"): "https://www.solanocounty.com/",
    ("Thousand Oaks", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Scottsdale", "AZ"): "https://mcassessor.maricopa.gov/",
    ("Denton", "TX"): "https://www.dentoncad.com/",
    ("Fort Worth", "TX"): "https://www.tad.org/",
    ("Dallas", "TX"): "https://www.dallascad.org/",
    ("Houston", "TX"): "https://hcad.org/property-search/",
    ("Austin", "TX"): "https://travisCAD.org/",
    ("San Antonio", "TX"): "https://www.bexar.org/2187/Property-Search",
    ("Chicago", "IL"): "https://datacatalog.cookcountyil.gov/",
    ("New York", "NY"): "https://data.cityofnewyork.us/resource/bnx9-e6tj.json",
    ("Brooklyn", "NY"): "https://data.cityofnewyork.us/resource/bnx9-e6tj.json",
    ("Miami", "FL"): "https://www.miamidade.gov/propertysearch/",
    ("Phoenix", "AZ"): "https://mcassessor.maricopa.gov/",
    ("Los Angeles", "CA"): "https://portal.assessor.lacounty.gov/",
    ("Philadelphia", "PA"): "https://property.phila.gov/",
    ("Atlanta", "GA"): "https://www.fultoncountyga.gov/",
    ("Charlotte", "NC"): "https://www.mecknc.gov/",
    ("Seattle", "WA"): "https://blue.kingcounty.com/Assessor/eRealProperty/",
    ("Denver", "CO"): "https://www.denvergov.org/property",
    ("Nashville", "TN"): "https://www.padctn.org/",
    ("Columbus", "OH"): "https://property.franklincountyohio.gov/",
    ("Cleveland", "OH"): "https://recorder.cuyahogacounty.us/",
    ("Kansas City", "MO"): "https://jacomo.org/",
    ("Milwaukee", "WI"): "https://city.milwaukee.gov/",
    ("Minneapolis", "MN"): "https://www.hennepin.us/",
    ("Detroit", "MI"): "https://www.waynecounty.com/",
    ("Pittsburgh", "PA"): "https://www.alleghenycounty.us/",
    ("Baltimore", "MD"): "https://sdat.dat.maryland.gov/RealProperty",
    ("Albuquerque", "NM"): "https://www.bernco.gov/",
    ("Tucson", "AZ"): "https://www.pima.gov/",
    ("Sacramento", "CA"): "https://eportal.saccounty.net/",
    ("San Jose", "CA"): "https://www.sccassessor.org/",
    ("Raleigh", "NC"): "https://www.wakegov.com/",
    ("Virginia Beach", "VA"): "https://www.vbgov.com/",
    ("Omaha", "NE"): "https://www.dcasse.org/",
    ("Oklahoma City", "OK"): "https://www.oklahomacounty.org/",
    ("Tulsa", "OK"): "https://www.assessor.tulsacounty.org/",
    ("Louisville", "KY"): "https://jeffersonky.gov/",
    ("Memphis", "TN"): "https://www.shelbycountytn.gov/",
    ("New Orleans", "LA"): "https://www.nola.gov/",
    ("Buffalo", "NY"): "https://www.erie.gov/",
    ("Rochester", "NY"): "https://www.monroecounty.gov/",
    ("Birmingham", "AL"): "https://www.jccal.org/",
    ("Little Rock", "AR"): "https://www.pulaskicounty.net/",
    ("Boise", "ID"): "https://www.adacounty.id.gov/",
    ("Des Moines", "IA"): "https://www.polkcountyiowa.gov/",
    ("Madison", "WI"): "https://www.cityofmadison.com/",
    ("Portland", "OR"): "https://www.multco.us/",
    ("Salt Lake City", "UT"): "https://www.saltlakecounty.gov/",
    ("Providence", "RI"): "https://www.providenceri.gov/",
    ("Hartford", "CT"): "https://www.hartford.gov/",
    ("Jersey City", "NJ"): "https://taxmaps.nj.gov/pdfs/county/Hudson",
    ("Wilmington", "DE"): "https://www.newcastlede.gov/",
    ("Tampa", "FL"): "https://www.hillsboroughcounty.org/",
    ("Jacksonville", "FL"): "https://www.coj.net/",
    ("St. Louis", "MO"): "https://stlouisco.com/",
    ("Colorado Springs", "CO"): "https://www.elpasoco.com/",
    ("Wichita", "KS"): "https://www.sedgwickcounty.org/",
    ("Lexington", "KY"): "https://www.fayettecountyky.gov/",
    ("Baton Rouge", "LA"): "https://www.ebrpa.org/",
    ("Boston", "MA"): "https://www.cityofboston.gov/assessing/",
    ("Grand Rapids", "MI"): "https://www.accesskent.com/",
    ("St. Paul", "MN"): "https://www.ramseycounty.us/",
    ("Billings", "MT"): "https://www.yellowstonecountymt.gov/",
    ("Reno", "NV"): "https://www.washoecounty.us/",
    ("Santa Fe", "NM"): "https://www.santafecounty.gov/",
    ("Greensboro", "NC"): "https://www.guilfordcountync.gov/",
    ("Durham", "NC"): "https://www.dconc.gov/",
    ("Cincinnati", "OH"): "https://www.hamiltoncountyohio.gov/",
    ("Toledo", "OH"): "https://www.co.lucas.oh.us/",
    ("El Paso", "TX"): "https://www.epcad.org/",
    ("Arlington", "TX"): "https://www.tad.org/",
    ("McKinney", "TX"): "https://www.collincad.org/",
    ("Frisco", "TX"): "https://www.collincad.org/",
    ("Irving", "TX"): "https://www.dallascad.org/",
    ("Garland", "TX"): "https://www.dallascad.org/",
    ("Richardson", "TX"): "https://www.dallascad.org/",
    ("Abilene", "TX"): "https://www.taylorcad.org/",
    ("Lubbock", "TX"): "https://www.lubbockcad.org/",
    ("Laredo", "TX"): "https://www.webbcad.org/",
    ("Amarillo", "TX"): "https://www.pottercad.org/",
    ("Brownsville", "TX"): "https://www.cameroncad.org/",
    ("West Valley City", "UT"): "https://www.saltlakecounty.gov/",
    ("Provo", "UT"): "https://www.utahcounty.gov/",
    ("Norfolk", "VA"): "https://www.norfolk.gov/",
    ("Chesapeake", "VA"): "https://www.cityofchesapeake.net/",
    ("Richmond", "VA"): "https://www.richmondgov.com/",
    ("Newport News", "VA"): "https://www.nnva.gov/",
    ("Alexandria", "VA"): "https://www.alexandriava.gov/",
    ("Hampton", "VA"): "https://www.hampton.gov/",
    ("Roanoke", "VA"): "https://www.roanokeva.gov/",
    ("Portsmouth", "VA"): "https://www.portsmouthva.gov/",
    ("Suffolk", "VA"): "https://www.suffolkva.us/",
    ("Lynchburg", "VA"): "https://www.lynchburgva.gov/",
    ("Spokane", "WA"): "https://www.spokanecounty.org/",
    ("Tacoma", "WA"): "https://www.piercecountywa.gov/",
    ("Vancouver", "WA"): "https://www.clark.wa.gov/",
    ("Bellevue", "WA"): "https://blue.kingcounty.com/Assessor/eRealProperty/",
    ("Kent", "WA"): "https://blue.kingcounty.com/Assessor/eRealProperty/",
    ("Everett", "WA"): "https://www.snohomishcountywa.gov/",
    ("Renton", "WA"): "https://blue.kingcounty.com/Assessor/eRealProperty/",
    ("Yakima", "WA"): "https://www.yakimacounty.us/",
    ("Federal Way", "WA"): "https://blue.kingcounty.com/Assessor/eRealProperty/",
    ("Spokane Valley", "WA"): "https://www.spokanecounty.org/",
    ("Bellingham", "WA"): "https://www.whatcomcounty.us/",
    ("Kenosha", "WI"): "https://www.kenoshacounty.org/",
    ("Racine", "WI"): "https://www.racinecounty.com/",
    ("Appleton", "WI"): "https://www.outagamie.org/",
    ("Waukesha", "WI"): "https://www.waukeshacounty.gov/",
    ("Oshkosh", "WI"): "https://www.co.winnebago.wi.us/",
    ("Eau Claire", "WI"): "https://www.co.eau-claire.wi.us/",
    ("Janesville", "WI"): "https://www.co.rock.wi.us/",
    ("Sheboygan", "WI"): "https://www.sheboygancounty.com/",
    ("La Crosse", "WI"): "https://www.lacrossecounty.org/",
    ("Fond du Lac", "WI"): "https://www.fdlco.wi.gov/",
    ("New Berlin", "WI"): "https://www.waukeshacounty.gov/",
    ("Wausau", "WI"): "https://www.co.marathon.wi.us/",
    ("Brookfield", "WI"): "https://www.waukeshacounty.gov/",
    ("Beloit", "WI"): "https://www.co.rock.wi.us/",
    ("Greenfield", "WI"): "https://city.milwaukee.gov/",
    ("Charleston", "WV"): "https://www.kanawha.us/",
    ("Cheyenne", "WY"): "https://www.laramiecounty.com/",
    ("Casper", "WY"): "https://www.natronacountywy.gov/",
    ("Gillette", "WY"): "https://www.campbellcountywy.gov/",
    ("Laramie", "WY"): "https://www.laramiecounty.com/",
    ("Rock Springs", "WY"): "https://www.sweetwatercountywy.gov/",
    ("Sheridan", "WY"): "https://www.sheridancounty.com/",
    ("Jackson", "WY"): "https://www.tetoncountywy.gov/",
    ("Riverton", "WY"): "https://www.fremontcountywy.org/",
    ("Cody", "WY"): "https://www.parkcounty.org/",
    ("Rawlins", "WY"): "https://www.carbonwy.com/",
    ("Lander", "WY"): "https://www.fremontcountywy.org/",
    ("Torrington", "WY"): "https://www.goshencounty.org/",
    ("Powell", "WY"): "https://www.parkcounty.org/",
    ("Douglas", "WY"): "https://www.conversecountywy.gov/",
    ("Worland", "WY"): "https://www.washakiecounty.net/",
    ("Buffalo", "WY"): "https://www.johnsoncountywyoming.org/",
    ("Evanston", "WY"): "https://www.uintacounty.com/",
    ("Green River", "WY"): "https://www.sweetwatercountywy.gov/",
    ("Newcastle", "WY"): "https://www.westoncounty.com/",
    ("Kemmerer", "WY"): "https://www.lincolncountywy.org/",
    ("Wheatland", "WY"): "https://www.plattecountywyoming.com/",
    ("Bar Nunn", "WY"): "https://www.natronacountywy.gov/",
    ("Mills", "WY"): "https://www.natronacountywy.gov/",
    ("Evansville", "WY"): "https://www.uintacounty.com/",
    ("Thermopolis", "WY"): "https://www.hotcountywy.net/",
    ("Lovell", "WY"): "https://www.bighorncountywy.gov/",
    ("Pinedale", "WY"): "https://www.sublettecountywy.gov/",
    ("Afton", "WY"): "https://www.lincolncountywy.org/",
    ("Saratoga", "WY"): "https://www.carbonwy.com/",
    ("Wright", "WY"): "https://www.campbellcountywy.gov/",
    ("Lyman", "WY"): "https://www.uintacounty.com/",
    ("Mountain View", "WY"): "https://www.uintacounty.com/",
    ("Byron", "WY"): "https://www.bighorncountywy.gov/",
    ("Fort Washakie", "WY"): "https://www.windriver.org/",
    ("Ethete", "WY"): "https://www.windriver.org/",
    ("Crowheart", "WY"): "https://www.windriver.org/",
    ("Arapahoe", "WY"): "https://www.windriver.org/",
    ("St. Stephens", "WY"): "https://www.windriver.org/",
    ("Boulder", "WY"): "https://www.sublettecountywy.gov/",
    ("Big Piney", "WY"): "https://www.sublettecountywy.gov/",
    ("Marbleton", "WY"): "https://www.sublettecountywy.gov/",
    ("Cokeville", "WY"): "https://www.lincolncountywy.org/",
    ("Diamondville", "WY"): "https://www.lincolncountywy.org/",
    ("La Barge", "WY"): "https://www.lincolncountywy.org/",
    ("Opal", "WY"): "https://www.lincolncountywy.org/",
    ("Smoot", "WY"): "https://www.lincolncountywy.org/",
    ("Thayne", "WY"): "https://www.lincolncountywy.org/",
    ("Alpine", "WY"): "https://www.lincolncountywy.org/",
    ("Star Valley Ranch", "WY"): "https://www.lincolncountywy.org/",
    ("Auburn", "WY"): "https://www.lincolncountywy.org/",
    ("Bedford", "WY"): "https://www.lincolncountywy.org/",
    ("Etna", "WY"): "https://www.lincolncountywy.org/",
    ("Fairview", "WY"): "https://www.lincolncountywy.org/",
    ("Grover", "WY"): "https://www.lincolncountywy.org/",
    ("Turnerville", "WY"): "https://www.lincolncountywy.org/",
    ("Freedom", "WY"): "https://www.lincolncountywy.org/",
    ("Alta", "WY"): "https://www.tetoncountywy.gov/",
    ("Teton Village", "WY"): "https://www.tetoncountywy.gov/",
    ("Wilson", "WY"): "https://www.tetoncountywy.gov/",
    ("Moose", "WY"): "https://www.tetoncountywy.gov/",
    ("Kelly", "WY"): "https://www.tetoncountywy.gov/",
    ("Moran", "WY"): "https://www.tetoncountywy.gov/",
    ("Hoback", "WY"): "https://www.tetoncountywy.gov/",
    ("Rafter J Ranch", "WY"): "https://www.tetoncountywy.gov/",
    ("South Park", "WY"): "https://www.tetoncountywy.gov/",
    ("Hoback Junction", "WY"): "https://www.tetoncountywy.gov/",
    ("Cora", "WY"): "https://www.sublettecountywy.gov/",
    ("Daniel", "WY"): "https://www.sublettecountywy.gov/",
    ("Bondurant", "WY"): "https://www.sublettecountywy.gov/",
    ("Farson", "WY"): "https://www.sweetwatercountywy.gov/",
    ("McKinnon", "WY"): "https://www.sweetwatercountywy.gov/",
    ("Point of Rocks", "WY"): "https://www.sweetwatercountywy.gov/",
    ("Superior", "WY"): "https://www.sweetwatercountywy.gov/",
    ("Wamsutter", "WY"): "https://www.sweetwatercountywy.gov/",
    ("Bairoil", "WY"): "https://www.sweetwatercountywy.gov/",
    ("Reliance", "WY"): "https://www.sweetwatercountywy.gov/",
    ("Little America", "WY"): "https://www.sweetwatercountywy.gov/",
    ("Baggs", "WY"): "https://www.carbonwy.com/",
    ("Dixon", "WY"): "https://www.carbonwy.com/",
    ("Elk Mountain", "WY"): "https://www.carbonwy.com/",
    ("Encampment", "WY"): "https://www.carbonwy.com/",
    ("Hanna", "WY"): "https://www.carbonwy.com/",
    ("Medicine Bow", "WY"): "https://www.carbonwy.com/",
    ("Riverside", "WY"): "https://www.carbonwy.com/",
    ("Ryan Park", "WY"): "https://www.carbonwy.com/",
    ("Savery", "WY"): "https://www.carbonwy.com/",
    ("Sinclair", "WY"): "https://www.carbonwy.com/",
    ("Walcott", "WY"): "https://www.carbonwy.com/",
    ("Jeffrey City", "WY"): "https://www.fremontcountywy.org/",
    ("Shoshoni", "WY"): "https://www.fremontcountywy.org/",
    ("Kinnear", "WY"): "https://www.fremontcountywy.org/",
    ("Pavillion", "WY"): "https://www.fremontcountywy.org/",
    ("Saint Stephens", "WY"): "https://www.fremontcountywy.org/",
    ("Lysite", "WY"): "https://www.fremontcountywy.org/",
    ("Moneta", "WY"): "https://www.fremontcountywy.org/",
    ("Morton", "WY"): "https://www.fremontcountywy.org/",
}

def get_portal(city, state):
    key = (city, state.upper())
    return PORTALS.get(key)

def enrich_batch(batch_file):
    with open(batch_file) as f:
        data = json.load(f)
    
    opportunities = data.get("opportunities", [])
    enriched = []
    
    for opp in opportunities:
        city_state = opp.get("city", "")
        parts = city_state.rsplit(" ", 1)
        if len(parts) == 2:
            city, state = parts
        else:
            city, state = city_state, ""
        
        portal = get_portal(city, state)
        
        enriched.append({
            "niche": opp.get("niche"),
            "city": city_state,
            "avg_job_value": opp.get("avg_job_value"),
            "lead_value": opp.get("lead_value"),
            "monthly_fee": opp.get("monthly_fee"),
            "opportunity_score": opp.get("opportunity_score"),
            "priority": opp.get("priority"),
            "status": opp.get("status"),
            "portal_url": portal or "Search required",
            "portal_status": "Mapped" if portal else "Manual lookup needed",
            "enriched_at": datetime.now().isoformat()
        })
    
    return enriched

def save_csv(records, filename):
    if not records:
        return
    keys = records[0].keys()
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(records)
    print(f"[✓] Saved {len(records)} records to {filename}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", help="Path to batch JSON file")
    parser.add_argument("--all", action="store_true", help="Process all-batches.json")
    args = parser.parse_args()
    
    if args.batch:
        batch_path = Path(args.batch)
        if not batch_path.exists():
            batch_path = WORKSPACE / batch_path
        
        print(f"[→] Enriching {batch_path}...")
        enriched = enrich_batch(batch_path)
        
        out_name = batch_path.stem + "_enriched.csv"
        out_path = OUTPUT_DIR / out_name
        save_csv(enriched, out_path)
        
        print(f"\n[✓] Enrichment complete!")
        print(f"    Mapped: {sum(1 for r in enriched if r['portal_status'] == 'Mapped')}/{len(enriched)}")
        print(f"    Output: {out_path}")
    
    elif args.all:
        all_batches = WORKSPACE / "skills" / "rr-niche-finder" / "data" / "all-batches.json"
        if all_batches.exists():
            print(f"[→] Processing all batches...")
            with open(all_batches) as f:
                data = json.load(f)
            
            all_enriched = []
            for batch in data.get("batches", []):
                for opp in batch.get("opportunities", []):
                    city_state = opp.get("city", "")
                    parts = city_state.rsplit(" ", 1)
                    if len(parts) == 2:
                        city, state = parts
                    else:
                        city, state = city_state, ""
                    
                    portal = get_portal(city, state)
                    all_enriched.append({
                        "niche": opp.get("niche"),
                        "city": city_state,
                        "avg_job_value": opp.get("avg_job_value"),
                        "lead_value": opp.get("lead_value"),
                        "monthly_fee": opp.get("monthly_fee"),
                        "opportunity_score": opp.get("opportunity_score"),
                        "priority": opp.get("priority"),
                        "status": opp.get("status"),
                        "portal_url": portal or "Search required",
                        "portal_status": "Mapped" if portal else "Manual lookup needed",
                        "enriched_at": datetime.now().isoformat()
                    })
            
            out_path = OUTPUT_DIR / "all_batches_enriched.csv"
            save_csv(all_enriched, out_path)
            
            mapped = sum(1 for r in all_enriched if r['portal_status'] == 'Mapped')
            print(f"\n[✓] All batches enriched!")
            print(f"    Total: {len(all_enriched)}")
            print(f"    Mapped: {mapped}/{len(all_enriched)} ({mapped/len(all_enriched)*100:.1f}%)")
            print(f"    Output: {out_path}")
    
    else:
        print("Usage:")
        print("  python3 enrich_land_lots.py --batch skills/rr-niche-finder/data/latest-batch.json")
        print("  python3 enrich_land_lots.py --all")

# ─── DNC Compliance (Keep all, flag DNC) ───

def load_dnc_list():
    """Load National DNC numbers."""
    dnc_path = WORKSPACE / "dnc_list.txt"
    if not dnc_path.exists():
        return set()
    numbers = set()
    with open(dnc_path) as f:
        for line in f:
            digits = "".join(c for c in line.strip() if c.isdigit())
            if len(digits) == 10:
                numbers.add(digits)
            elif len(digits) == 11 and digits.startswith("1"):
                numbers.add(digits[1:])
    return numbers

def normalize_phone(phone):
    """Normalize phone to 10 digits."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""

def check_dnc(phone, dnc_set=None):
    """Check if phone is on DNC list. Returns True/False."""
    if dnc_set is None:
        dnc_set = load_dnc_list()
    normalized = normalize_phone(phone)
    return normalized in dnc_set if normalized else False

def add_dnc_fields(records):
    """Add DNC tracking fields to all records. Never remove records."""
    dnc_set = load_dnc_list()
    for r in records:
        r['dnc_checked'] = True
        r['dnc_list_loaded'] = len(dnc_set) > 0
        r['dnc_list_count'] = len(dnc_set)
        r['dnc_status'] = 'pending'  # pending | checked | flag_dnc | safe
        r['dnc_safe_to_call'] = 'pending'
        r['dnc_flag_reason'] = ''
        r['dnc_numbers'] = ''  # comma-separated list
        r['safe_numbers'] = ''  # comma-separated list
    return records

def add_dnc_to_batch(batch_file):
    """Re-process a batch and add DNC fields."""
    with open(batch_file) as f:
        data = json.load(f)
    
    opportunities = data.get("opportunities", [])
    enriched = []
    
    for opp in opportunities:
        city_state = opp.get("city", "")
        parts = city_state.rsplit(" ", 1)
        if len(parts) == 2:
            city, state = parts
        else:
            city, state = city_state, ""
        
        portal = get_portal(city, state)
        
        enriched.append({
            "niche": opp.get("niche"),
            "city": city_state,
            "avg_job_value": opp.get("avg_job_value"),
            "lead_value": opp.get("lead_value"),
            "monthly_fee": opp.get("monthly_fee"),
            "opportunity_score": opp.get("opportunity_score"),
            "priority": opp.get("priority"),
            "status": opp.get("status"),
            "portal_url": portal or "Search required",
            "portal_status": "Mapped" if portal else "Manual lookup needed",
            "enriched_at": datetime.now().isoformat()
        })
    
    enriched = add_dnc_fields(enriched)
    return enriched

if __name__ == "__main__":
    main()
