# retrieve_tables/controllers_local.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

import json
import os
import time

import requests
import sqlalchemy as sa
from django.http import HttpResponse

import wevote_functions.admin
from config.base import get_environment_variable
from retrieve_tables.retrieve_common import allowable_tables
from wevote_functions.functions import get_voter_api_device_id, positive_value_exists

logger = wevote_functions.admin.get_logger(__name__)

t0 = 0
global_stats = {}
dummy_unique_id = 10000000
LOCAL_TMP_PATH = '/tmp/'
AWS_ACCESS_KEY_ID = get_environment_variable("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = get_environment_variable("AWS_SECRET_ACCESS_KEY")
AWS_REGION_NAME = get_environment_variable("AWS_REGION_NAME")
AWS_STORAGE_BUCKET_NAME = get_environment_variable("AWS_STORAGE_BUCKET_NAME")
AWS_STORAGE_SERVICE = "s3"


def update_fast_load_db(host, voter_api_device_id, table_name, additional_records):
    """
    Updates progress bar and data on fast load HTML page
    :param host:
    :param voter_api_device_id:
    :param table_name:
    :param additional_records:
    :return:
    """
    try:
        response = requests.get(host + '/apis/v1/fastLoadStatusUpdate/',
                                verify=True,
                                params={'table_name': table_name,
                                        'additional_records': additional_records,
                                        'is_running': True,
                                        'voter_api_device_id': voter_api_device_id,
                                        })

        # print('update_fast_load_db ', response.status_code, response.url, voter_api_device_id)
        # print(response.request.url)
        print('update_fast_load_db ', response.status_code, response.url, voter_api_device_id)
    except Exception as e:
        logger.error('update_fast_load_db caught: ', str(e))


def retrieve_sql_files_from_master_server(request):
    results = {}
    # noinspection PyShadowingNames
    t0 = time.time()

    # ONLY CHANGE host to 'wevotedeveloper.com' while debugging the fast load code, where Master and Client are the same
    # host = 'https://wevotedeveloper.com:8000'
    host = 'https://api.wevoteusa.org'
    voter_api_device_id = get_voter_api_device_id(request)

    try:
        # hack, call master from local...
        # results = backup_one_table_to_s3_controller('id', 'ballot_ballotitem')
        # ballot_ballotitem has 40,999,358 records in December 2024 and takes about 69 seconds to dump and 10 more to
        # upload on the master servers (simulated on my fast Mac with fast Internet).  These s3 files are set to expire
        # in a day
        # Example: https://wevote-images.s3.amazonaws.com/backup-ballot_ballotitem-2024-12-06T13:25:13.backup
        # This same backup file takes 21 seconds to download to a local tempfile, and then 3 seconds to pg_restore

        num_tables = len(allowable_tables)
        print(f"Fast loading {num_tables} tables")
        global_stats['num_tables'] = num_tables
        global_stats['count'] = 0
        global_stats['step'] = 0
        global_stats['elapsed'] = 0

        for table_name in allowable_tables:
            t1 = time.time()
            global_stats['table_name_text'] = ('<b>Saving</b>&nbsp;&nbsp;<i>' + table_name +
                                          '</i>&nbsp;&nbsp;to s3 from the <b>master</b> server')
            global_stats['table_name'] = table_name
            global_stats['count'] += 1
            global_stats['step'] += 1
            global_stats['elapsed'] = int(time.time() - t0)
            print(f"{global_stats['count']} -- Retrieving table {table_name}")
            url = f'{host}/apis/v1/backupOneTableToS3/'
            params = {'table_name': table_name, 'voter_api_device_id': voter_api_device_id}
            structured_json = fetch_data_from_api(url, params, 100, 180)  # 3 min timeout for ballot_i
            aws_s3_file_url = structured_json['aws_s3_file_url']
            print(f"{global_stats['count']} -- Intermediate aws file {aws_s3_file_url} "
                  f"received at {time.time()-t1} seconds")

            time.sleep(0.5)

            global_stats['table_name_text'] = ('<b>Loading</b>&nbsp;&nbsp;<i>' + table_name +
                                          '</i>&nbsp;&nbsp;from s3 on the <b>local</b> server')
            # restore_one_file_to_local_server(aws_s3_file_url, 'ballot_ballotitem')
            restore_one_file_to_local_server(aws_s3_file_url, table_name)
            global_stats['step'] += 1
            print(f"{global_stats['count']} -- Restored table {table_name} at {time.time()-t1} seconds")

        print(f"All {num_tables} tables fast loaded in {time.time() - t0} seconds")

    except Exception as e:
        results['status'] = 'Error ' + str(e)
        logger.error(f"Error retrieving {str(e)}")

    return HttpResponse(json.dumps(results), content_type='application/json')


def restore_one_file_to_local_server(aws_s3_file_url, table_name):
    import boto3
    import tempfile
    results = {
        'success': False
    }

    try:
        # s3 = boto3.client('s3')
        session = boto3.session.Session(region_name=AWS_REGION_NAME,
                                        aws_access_key_id=AWS_ACCESS_KEY_ID,
                                        aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        s3 = session.resource(AWS_STORAGE_SERVICE)

        head, tail = os.path.split(aws_s3_file_url)

        diff_t0 = time.time() - t0
        print(f"About to download {table_name} from S3 at {diff_t0:.2f} seconds")
        tf = tempfile.NamedTemporaryFile(mode='r+b')
        print(f"AWS_STORAGE_BUCKET_NAME: {AWS_STORAGE_BUCKET_NAME}, tail: {tail}, tf.name: {tf.name}")
        s3.Bucket(AWS_STORAGE_BUCKET_NAME).download_file(tail, tf.name)
        print("Downloaded", tf.name)
        diff_t0 = time.time() - t0
        print("Done with download from S3 at {:.6f} seconds".format(diff_t0))
    except Exception as e:
        print("!!Problem occurred Downloading file:", e)
        results['success'] = False,
        results['error string'] = str(e)
        return results

    try:
        db_name = get_environment_variable("DATABASE_NAME")
        db_user = get_environment_variable('DATABASE_USER')
        # db_password = get_environment_variable('DATABASE_PASSWORD') No need to use the developers db password (so far)
        db_host = get_environment_variable('DATABASE_HOST')
        db_port = get_environment_variable('DATABASE_PORT')

        diff_t0 = time.time() - t0
        print("About to drop_table {} at {:.6f} seconds".format(table_name, diff_t0))
        engine = connect_to_db()
    except Exception as e:
        print("!!Problem occurred connecting to db:", e)
        results['success'] = False,
        results['error string'] = str(e)
        return results

    try:
        drop_table(engine, table_name)

        diff_t0 = time.time() - t0
        print("About to pg_restore from tempfile at {:.6f} seconds".format(diff_t0))

        command_str = f"pg_restore -v --data-only --disable-triggers -U {db_user} "
        if positive_value_exists(db_host):
            command_str += f"-h {db_host} "
        if positive_value_exists(db_port):
            command_str += f"-p {db_port} "
        command_str += f"-d {db_name} -t {table_name} "
        command_str += f"\"{tf.name}\""
        print(command_str)

        os.system(command_str)

        diff_t0 = time.time() - t0
        print("Restore completed at {:.6f} seconds".format(diff_t0))
        results['success'] = True
    except Exception as e:
        print("!!Problem occurred 2!!", e)
        results['success'] = False,
        results['error string'] = str(e)

    return results


# noinspection PyUnusedLocal
def get_local_fast_load_status(request):
    # print("Getting local fast load status", global_stats)
    return HttpResponse(json.dumps(global_stats), content_type='application/json')


def connect_to_db():
    """
    Create a connection with the local postgres database with sqlalchemy and psycopg2
    :return:
    """
    try:
        connection_string = f"postgresql+psycopg2://{get_environment_variable('DATABASE_USER')}"
        if positive_value_exists(get_environment_variable('DATABASE_PASSWORD')):
            connection_string += f":{get_environment_variable('DATABASE_PASSWORD')}"
        connection_string += f"@{get_environment_variable('DATABASE_HOST')}"
        if positive_value_exists(get_environment_variable('DATABASE_PORT')):
            connection_string += f":{get_environment_variable('DATABASE_PORT')}"
        connection_string += f"/{get_environment_variable('DATABASE_NAME')}"
        engine = sa.create_engine(connection_string)
        return engine
    except Exception as e:
        logger.error('Unable to connect to database: ', str(e))


def drop_table(engine, table_name):
    """
    Truncates (completely clears contents of) local table
    :param engine: connection to local Postgres
    :param table_name: table to truncate
    :return:
    """
    with engine.connect() as conn:
        try:
            # Drop the table
            conn.execute(sa.text(f"DROP TABLE {table_name}"))
            print(f"RUNNING: DROP TABLE {table_name} ")
        except Exception as e:
            logger.error(f'FAILED_TABLE_DROP: {table_name} -- {str(e)}')


def fetch_data_from_api(url, params, max_retries=1000, timeout=8):
    """
    Fetches data from remote Postgres database
    :param url:
    :param params:
    :param max_retries:
    :return:
    """
    for attempt in range(max_retries):
        # print(f'Attempt {attempt} of {max_retries} attempts to fetch data from api')
        try:
            response = requests.get(url, params=params, verify=True, timeout=timeout)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"\nAPI request failed with status code {response.status_code}, retrying...")
        except requests.Timeout:
            logger.error(f"Request timed out, retrying...\n{url} params: {params}")
        except requests.RequestException as e:
            logger.error(f"API request failed: {e}, retrying...")
        time.sleep(2 ** attempt)  # Exponential backoff

    raise Exception("API request failed after maximum retries")


# -------------------- Below this line is the code for the old way that did not use s3 and did not need the same
# -------------------- versions of pg_dump and postgres on both the local and the master servers  12/6/24

#
# def save_off_database():
#     file = "WeVoteServerDB-{:.0f}.pgsql".format(time.time())
#     os.environ['PATH'] = '/opt/homebrew/bin:' + os.environ['PATH']
#     os.system('pg_dump WeVoteServerDB > ' + file)
#     time.sleep(20)
#
#
#
#
# def get_max_id(params):
#     """
#     Gets the maximum id present in the remote Postgres table
#     :param params: list of parameters to pass to API
#     :return: response.json()
#     """
#     host = 'https://api.wevoteusa.org'
#     try:
#         response = requests.get(host + '/apis/v1/retrieveMaxID', params=params)
#         if response.status_code == 200:
#             return response.json()
#         else:
#             print(f"API request failed with status code {response.status_code}")
#             return -1
#     except Exception as e:
#         print(f"ROW_COUNT_ERROR: {str(e)}", )
#
#
# def retrieve_sql_files_from_master_server(request):
#     results = {}
#     t0 = time.time()
#     try:
#         # hack, call master from local
#         # results = backup_one_table_to_s3(request)
#         # con = results.content
#
#         aws_s3_file_url = ('nonsense')
#         # restore_one_file_to_local_server(aws_s3_file_url, 'ballot_ballotitem')
#     except Exception as e:
#         results['status'] = 'Error ' + str(e)
#
#
#     return HttpResponse(json.dumps(results), content_type='application/json')
#
#
# def restore_one_file_to_local_server_experimental(aws_s3_file_url, table_name):
#     import boto3
#     import tempfile
#     results = {}
#
#     s3 = boto3.client('s3')
#
#     AWS_STORAGE_BUCKET_NAME = get_environment_variable("AWS_STORAGE_BUCKET_NAME")
#     head, tail = os.path.split(aws_s3_file_url)
#
#     diff_t0 = time.time() - t0
#     print("About to download from S3 at {:.6f} seconds".format(diff_t0))
#     tf = tempfile.NamedTemporaryFile(mode='r+b')
#     s3.download_file(AWS_STORAGE_BUCKET_NAME, tail, tf.name)
#     diff_t0 = time.time() - t0
#     print("Done with download from S3 at {:.6f} seconds".format(diff_t0))
#
#     try:
#         db_name = get_environment_variable("DATABASE_NAME"),
#         db_user = get_environment_variable('DATABASE_USER'),
#         db_password = get_environment_variable('DATABASE_PASSWORD'),
#         db_host = get_environment_variable('DATABASE_HOST'),
#         db_port = get_environment_variable('DATABASE_PORT')
#
#         # 'pg_restore -a -t your_table /path/to/dump.sql'
#         # '-h {db_host[0]} -p {db_port} -d {db_name[0]} -U {db_user[0]} -t {table_name}'
#
#         diff_t0 = time.time() - t0
#         print("About to drop_table {} at {:.6f} seconds".format(table_name, diff_t0))
#         engine = connect_to_db()
#         drop_table(engine, table_name)
#
#         time.sleep(3)
#
#         diff_t0 = time.time() - t0
#         print("About to pg_restore from tempfile at {:.6f} seconds".format(diff_t0))
#
#    command_str = f"pg_restore --h {db_host[0]} -p {db_port} -d {db_name[0]} -U {db_user[0]} -t {table_name} {tf.name}"
#         os.system(command_str)
#
#         diff_t0 = time.time() - t0
#         print("Restore completed at {:.6f} seconds".format(diff_t0))
#         success = True
#     except Exception as e:
#         print("!!Problem occurred!!", e)
#         success = False,
#         results['error string'] = str(e)
#
#         # with open(aws_s3_file_url.path, "rb") as f:
#         #     dump_file_text = f.read()
#     return results
#
# def retrieve_sql_files_from_master_server_old (request):
#     """
#     Get the json data, and create new entries in the developers local database
#     Runs on the Local server (developer's Mac)
#     :return:
#     """
#     t0 = time.time()
#     engine = connect_to_db()
#     print(
#         '\nSaving off a copy of your local db (an an emergency fallback, that will almost never be needed) in '
#         '\'WeVoteServerDB-*.pgsql\' files, feel free to delete them at anytime')
#     # save_off_database()
#     dt = time.time() - t0
#     stats = {}
#     print('Saved off local database in ' + str(int(dt)) + ' seconds \n')
#     stats |= {'save_off': str(int(dt))}
#
#     # ONLY CHANGE host to 'wevotedeveloper.com' while debugging the fast load code, where Master and Client are  same
#     # host = 'https://wevotedeveloper.com:8000'
#     host = 'https://api.wevoteusa.org'
#     voter_api_device_id = get_voter_api_device_id(request)
#     requests.get(host + '/apis/v1/fastLoadStatusRetrieve',
#                  params={"initialize": True, "voter_api_device_id": voter_api_device_id}, verify=True)
#     for table_name in allowable_tables:
#         print(f"{table_name.upper()}\n--------------------")
#         truncate_table(engine, table_name)
#
#         max_id_params = {'table_name': table_name}
#         max_id_response = get_max_id(max_id_params)
#         max_id = max_id_response['maxID']
#         chunk_size = 10000
#         start = 0
#         end = chunk_size - 1
#         structured_json = {}
#         table_start_time = time.time()
#         # filling table with 10,000 line chunks
#         if max_id and max_id != -1:
#             while end - chunk_size < max_id:
#                 print(f"{table_name}:   {((start / max_id) * 100):.0f}% -- Chunk {start} to {end} of {max_id} rows")
#                 try:
#                     url = f'{host}/apis/v1/retrieveSQLTables/'
#                     params = {'table_name': table_name, 'start': start, 'end': end,
#                               'voter_api_device_id': voter_api_device_id}
#
#                     structured_json = fetch_data_from_api(url, params)
#                 except Exception as e:
#                     print(f"FETCH_ERROR: {table_name} -- {str(e)}")
#
#                 if not structured_json['success']:
#                     print(f"FAILED: Did not receive '{table_name}' from server")
#                     break
#                 try:
#                     data = structured_json['files'].get(table_name, "")
#                     split_data = data.splitlines(keepends=True)
#                     update_fast_load_db(host, voter_api_device_id, table_name, len(split_data))
#                     lines_count = process_table_data(table_name, split_data)
#                     # print(f'{lines_count} lines in chunk')
#                 except Exception as e:
#                     print(f"TABLE_PROCESSING_ERROR: {table_name} -- {str(e)}")
#                 start += chunk_size
#                 end += chunk_size
#
#             print(f'Table {table_name} took {((time.time() - table_start_time) / 60):.1f} min\n')
#
#             # reset table's id sequence
#             reset_id_seq(engine, table_name)
#         else:
#             print(f"{table_name} is empty\n")
#     minutes = (time.time() - t0) / 60
#     print(f"Total time for all tables: {minutes:.1f} minutes")
#     results = {'status': 'Completed', 'status_code': 200}
#     return HttpResponse(json.dumps(results), content_type='application/json')
#
#
# def truncate_table(engine, table_name):
#     """
#     Truncates (completely clears contents of) local table
#     :param engine: connection to local Postgres
#     :param table_name: table to truncate
#     :return:
#     """
#     with engine.connect() as conn:
#         try:
#             # Truncate the table
#             conn.execute(sa.text(f"TRUNCATE {table_name} RESTART IDENTITY CASCADE"))
#             print(f"RUNNING: TRUNCATE {table_name} RESTART IDENTITY CASCADE")
#         except Exception as e:
#             print(f'FAILED_TABLE_TRUNCATE: {table_name} -- {str(e)}')
#         # checking that table is actually empty before inserting new data
#         try:
#             result = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}"))
#             row_count = result.fetchone()[0]
#             if row_count > 0:
#                 print(f"Error: {table_name} is not empty after truncation")
#                 return
#         except Exception as e:
#             print(f"TRUNCATION_CHECK: {table_name} -- {str(e)}")
#
#
# def drop_table(engine, table_name):
#     """
#     Truncates (completely clears contents of) local table
#     :param engine: connection to local Postgres
#     :param table_name: table to truncate
#     :return:
#     """
#     with engine.connect() as conn:
#         try:
#             # Drop the table
#             conn.execute(sa.text(f"DROP {table_name}"))
#             print(f"RUNNING: DROP {table_name} ")
#         except Exception as e:
#             print(f'FAILED_TABLE_DROP: {table_name} -- {str(e)}')
#         # checking that table is actually empty before inserting new data
#         # try:
#         #     result = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}"))
#         #     row_count = result.fetchone()[0]
#         #     if row_count > 0:
#         #         print(f"Error: {table_name} is not empty after truncation")
#         #         return
#         # except Exception as e:
#         #     print(f"DROP_CHECK: {table_name} -- {str(e)}")


# def reset_id_seq(engine, table_name):
#     """
#     Resets id sequence of table
#     :param engine:
#     :param table_name:
#     :return:
#     """
#     with engine.connect() as conn:
#         try:
#             query = sa.text(f"""SELECT setval('{table_name}_id_seq', (SELECT MAX(id) FROM "{table_name}"))""")
#             result = conn.execute(query)
#             sequence_val = result.fetchone()[0]
#             if sequence_val is not None:
#                 query = sa.text(f"ALTER SEQUENCE {table_name}_id_seq RESTART WITH {int(sequence_val) + 1}")
#                 conn.execute(query)
#             # To confirm:  SELECT * FROM information_schema.sequences where sequence_name like 'org%'
#         except Exception as e:
#             print(f'...FAILED_SEQUENCE_RESET: {table_name} -- {str(e)}')
#
#
# def process_table_data(table_name, split_data):
#     """
#     Processes and inserts data into local Postgres table
#     :param table_name: target table to insert into
#     :param split_data: list of rows from data returned by API
#     :return:
#     """
#     # print("Processing data from API...")
#     first_len = len(split_data[0].split("|"))
#     lines = [line.split("|") for line in split_data if len(line.split("|")) == first_len]
#     # No valid lines to process for table. Skipping insertion.
#     if not lines:
#         return
#     engine = connect_to_db()
#
#     inspector = Inspector.from_engine(engine)
#     columns = inspector.get_columns(table_name)
#     # list of column names in the correct order
#     col_names = [col['name'] for col in columns]
#
#     df = pd.DataFrame(lines[1:], columns=lines[0])
#     # Strip extra whitespace from column names
#     df.columns = df.columns.str.strip()
#
#     # Ensure DataFrame has all columns from the table
#     for col in col_names:
#         if col not in df.columns:
#             df[col] = pd.NA  # Add missing columns with NaN values
#
#     # Reorder DataFrame columns to match the table schema
#     df = df[col_names]
#     # No valid data to insert for table. Skipping insertion
#     if df.empty:
#         return 0
#
#     # retrieve constraints from table
#     # Some unique_cols should not get dummy values, since these values are relied on as keys to other tables
#     do_not_touch = ['we_vote_id', 'voter_id', 'linked_campaignx_we_vote_id',
#                     'organization_we_vote_id', 'google_civic_election_id']
#     # removed  'linked_politician_we_vote_id',
#     unique_constraints = inspector.get_unique_constraints(table_name)
#     unique_cols = [con['column_names'][0] for con in unique_constraints]
#     unique_cols = [x for x in unique_cols if x not in do_not_touch]
#
#     # unique_cols = [con['column_names'][0] for (con in unique_constraints and con not in do_not_touch)]
#
#     foreign_keys = inspector.get_foreign_keys(table_name)
#     fk_cols = [col['constrained_columns'][0] for col in foreign_keys]
#
#     not_null_columns = []
#     col_dict = {}
#     df_cleaned = pd.DataFrame()
#     for col in columns:
#         if not col['nullable']:
#             not_null_columns.append(col['name'])
#         col_dict[col['name']] = str(col['type'])
#
#     with engine.connect() as conn:
#         max_id = fetch_local_max_id(conn, table_name, "id")
#     try:
#         df_cleaned = clean_df(df, col_dict, unique_cols, not_null_columns, fk_cols, max_id)
#     except Exception as e:
#         print(f"TABLE_CLEANING_ERROR: {str(e)}")
#     # No valid data to insert for {table_name}. Skipping insertion.
#     if df_cleaned.empty:
#         return 0
#
#     with engine.connect() as conn:
#         try:
#             # Write cleaned DataFrame to the PostgresSQL table
#             copy_df_to_postgres(df_cleaned, conn, table_name)
#         except Exception as e:
#             print(f"FAILED_TABLE_INSERT: {table_name} -- {str(e)}")
#     return len(df_cleaned)
#
#
# def clean_df(df, col_dict, unique_cols, not_null_columns, fk_cols, start_id):
#     """
#     Prepares the pandas DataFrame for insertion into the Postgres table
#     :param df: pandas DataFrame to be cleaned
#     :param col_dict: a dictionary with column name as key, column dtype as value
#     :param unique_cols: list of cols with unique value constraint
#     :param not_null_columns: list of cols with not-null constraint
#     :param fk_cols: list of cols with foreign key constraint
#     :param start_id: index of first row in the chunk
#     :return
#     """
#     df = df.apply(lambda col: col.replace('\\N', pd.NA)
#                   .str.replace(r'[\n,]', ' ', regex=True)
#                   .str.replace(r'[^0-9a-zA-Z\. _,]', '', regex=True) if col.dtype == 'object' else col)
#
#     # Remove leading and trailing whitespaces in each cell of df
#     df = strip_whitespace(df)
#
#     boolean_map = {
#         'True': 1, 'False': 0,
#         't': 1, 'f': 0,
#         '1': 1, '0': 0,
#         'yes': 1, 'no': 0
#     }
#     not_null_id_cols = []
#     boolean_columns = [col for col, dtype in col_dict.items() if dtype == "BOOLEAN" and col in df.columns]
#     timestamp_columns = [col for col, dtype in col_dict.items() if dtype == "TIMESTAMP" and col in df.columns]
#     integer_columns = [col for col, dtype in col_dict.items() if dtype in ["INTEGER", "BIGINT"] and col in df.columns]
#     double_precision_columns = [col for col, dtype in col_dict.items() if
#                                 dtype == "DOUBLE PRECISION" and col in df.columns]
#     date_columns = [col for col, dtype in col_dict.items() if dtype == "DATE" and col in df.columns]
#     varchar_cols = [col for col, dtype in col_dict.items() if "VARCHAR" in dtype and col in df.columns]
#
#     if boolean_columns:
#         df[boolean_columns] = df[boolean_columns].replace(r'^\s*$', pd.NA, regex=True).replace(boolean_map)
#         df[boolean_columns] = df[boolean_columns].fillna(False).astype(bool)
#     if timestamp_columns:
#         for col in timestamp_columns:
#             if col in not_null_columns:
#                 df[col] = df[col].replace(['', pd.NA, 'null'], datetime.now(timezone.utc))
#             df[col] = pd.to_datetime(df[col], errors='coerce', utc=True,
#                                      format="%Y-%m-%d %H:%M:%S")  # convert cols to datetime
#             df[col] = df[col].fillna(datetime.now(timezone.utc))  # Fill any NaT values that were created
#                                                                   # by conversion
#             if df[col].dt.tz is None:  # Convert to UTC timezone if not timezone specified
#                 df[col] = df[col].dt.tz_localize('UTC', ambiguous='NaT', nonexistent='NaT')
#             else:
#                 df[col] = df[col].dt.tz_convert('UTC')
#     if integer_columns:
#         # Separate those with and without fk constraints
#         non_fk_int_columns = [col for col in integer_columns if col not in fk_cols]
#         fk_integer_columns = [col for col in integer_columns if col in fk_cols]
#
#         if non_fk_int_columns:
#            df[non_fk_int_columns] = df[non_fk_int_columns].apply(pd.to_numeric, errors='coerce').fillna(0).astype(int)
#         if fk_integer_columns:
#             df[fk_integer_columns] = df[fk_integer_columns].apply(pd.to_numeric, errors='coerce')
#             df[fk_integer_columns] = df[fk_integer_columns].apply(lambda col: col.replace(pd.NA, None))
#
#         # Keep track of non-null ID columns
#         not_null_id_cols.extend([col for col in integer_columns if col in not_null_columns])
#     if double_precision_columns:
#         df[double_precision_columns] = df[double_precision_columns].replace(['False'], pd.NA)
#     if date_columns:
#         df[date_columns] = df[date_columns].apply(lambda col: col.replace(['', pd.NA, pd.NaT, 'null'], "1800-01-01"))
#     if varchar_cols:
#         cols_to_update = [col for col in varchar_cols if col in not_null_columns]
#         df[cols_to_update] = df[cols_to_update].apply(lambda col: col.replace('', ' '))
#
#     # add any column to this list if you know it doesn't have ids
#     dummy_cols = {'ballotpedia_election_id', 'bioguide_id', 'thomas_id', 'lis_id', 'govtrack_id', 'fec_id',
#                   'maplight_id'}
#     df = get_dummy_ids(df, dummy_cols, unique_cols, not_null_id_cols, start_id + 1)
#     return df
#
#
# def strip_whitespace(df):
#     """
#     Strips whitespace from every cell in the DataFrame.
#     """
#     str_columns = df.select_dtypes(include=['object'])
#     df[str_columns.columns] = str_columns.apply(lambda col: col.str.strip())
#     return df
#
#
# def get_row_count_from_master_server():
#     try:
#         host = 'https://api.wevoteusa.org'
#         response = requests.get(host + '/apis/v1/retrieveSQLTablesRowCount')
#         if response.status_code == 200:
#             count = int(response.json()['rowCount'])
#             return count
#         logger.error("retrieveSQLTablesRowCount received HTTP response " + str(response.status_code))
#         return -1
#     except Exception as e:
#         logger.error("retrieveSQLTablesRowCount row count error ", str(e))
#         return -1
#
#
# def fetch_local_max_id(conn, table_name, id_column):
#     """
#     Fetches the maximum ID value from a specified local table.
#     :param conn: SQLAlchemy connection object.
#     :param table_name: Name of the table to query.
#     :param id_column: Name of the ID column.
#     :return: Maximum ID value or 0 if the table is empty.
#     """
#     dbapi_conn = conn.connection
#     with dbapi_conn.cursor() as cursor:
#         cursor.execute(f"SELECT COALESCE(MAX({id_column}), 0) FROM {table_name}")
#         max_id = cursor.fetchone()[0]
#     return max_id
#
#
# def get_dummy_ids(df, dummy_cols, unique_cols, not_null_id_cols, start_id):
#     """
#     Generates unique id's for each row in dummy_cols, unique_constraints, not_null_id_cols
#     :param df:
#     :param dummy_cols: a list of col names that require unique id's for each row
#     :param unique_cols: a list of col names that have unique constraints
#     :param not_null_id_cols: a list of id columns that cannot contain null values
#     :param start_id: the index of the first row in the chunk
#     :return:
#     """
#     dummy_cols.update(set(unique_cols) - dummy_cols)
#     dummy_cols.update(set(not_null_id_cols) - dummy_cols)
#     dummy_cols = list(dummy_cols)
#     print('dummy_cols (replaced with a unique counter) ---> ', dummy_cols)
#
#     new_ids = np.arange(start_id, start_id + len(df))
#
#     # Replace the entire column with new IDs for each column that requires unique IDs
#     for col in dummy_cols:
#         if col in df.columns:
#             df[col] = new_ids
#
#     return df
#
#
# def copy_df_to_postgres(df: pd.DataFrame, conn, table_name):
#     """
#     Copies pandas DataFrame to local Postgres table
#     :param df: pandas DataFrame to copy
#     :param conn: connection to local postgres
#     :param table_name: name of table to copy into in local Postgres
#     :return:
#     """
#     if df.empty:
#         print("DataFrame is empty. Skipping insert.")
#         return
#
#     temp_dir = os.path.join(LOCAL_TMP_PATH, table_name)
#     os.makedirs(temp_dir, exist_ok=True)
#     temp_csv_path = os.path.join(temp_dir, f'{table_name}.csvTemp')
#     try:
#         df.to_csv(temp_csv_path, index=False, header=False, sep="|")
#     except Exception as e:
#         print(f"TO_CSV FAILED: {table_name} -- {str(e)}")
#
#     dbapi_conn = conn.connection
#     with dbapi_conn.cursor() as cursor:
#         try:
#             with open(temp_csv_path, 'r') as csv_file:
#                 cursor.copy_from(csv_file, table_name, sep='|', null="")
#             dbapi_conn.commit()
#         except (Exception, psycopg2.DatabaseError) as error:
#             print(f"FAILED_COPY_FROM: {str(error)}")
#         finally:
#             # Clean up by removing the temporary CSV file
#             os.remove(temp_csv_path)
