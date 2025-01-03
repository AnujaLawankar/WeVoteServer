import psycopg2

from config.base import get_environment_variable

# Security note: the master side of fast load will only return the data from the following table,
# Changing this table on local side by itself will not work

# The fast load apis will only return the data from the following tables
allowable_tables = [
    'position_positionentered',                      # Zero rows on master server Dec 2024
    'campaign_campaignx',                            # Zero rows on master server Dec 2024
    'campaign_campaignxowner',                       # 92 rows on master server Dec 2024
    'campaign_campaignxpolitician',                  # 50 rows on master server Dec 2024
    'campaign_campaignxlistedbyorganization',        # 1 row on master server Dec 2024
    'campaign_campaignxnewsitem',                    # Zero rows on master server Dec 2024
    'campaign_campaignxseofriendlypath',
    'campaign_campaignxsupporter',
    'candidate_candidatesarenotduplicates',          # 532 rows on master server Dec 2024
    'candidate_candidatetoofficelink',
    'election_ballotpediaelection',
    'election_election',
    'electoral_district_electoraldistrict',
    'issue_issue',
    'issue_organizationlinktoissue',
    'measure_contestmeasure',
    'measure_contestmeasuresarenotduplicates',
    'office_contestoffice',
    'office_contestofficesarenotduplicates',
    'office_contestofficevisitingotherelection',
    'office_held_officeheld',
    'organization_organizationreserveddomain',
    'party_party',
    'politician_politician',
    'politician_politiciansarenotduplicates',
    'representative_representative',
    'representative_representativesarenotduplicates',
    'twitter_twitterlinktoorganization',
    'voter_guide_voterguidepossibility',
    'voter_guide_voterguidepossibilityposition',
    'voter_guide_voterguide',
    'wevote_settings_wevotesetting',
    'ballot_ballotreturned',
    'polling_location_pollinglocation',
    'organization_organization',
    'candidate_candidatecampaign',
    'ballot_ballotitem',
]

def get_psycopg2_connection():
    conn = psycopg2.connect(
        database=get_environment_variable('DATABASE_NAME_READONLY'),
        user=get_environment_variable('DATABASE_USER_READONLY'),
        password=get_environment_variable('DATABASE_PASSWORD_READONLY'),
        host=get_environment_variable('DATABASE_HOST_READONLY'),
        port=get_environment_variable('DATABASE_PORT_READONLY')
    )
    return conn
