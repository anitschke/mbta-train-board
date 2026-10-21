from train_predictor import TrainPredictor, TrainPredictorDependencies, Direction, TrainWarning, TrainArrival
from datetime import datetime, timedelta
import time
import json
import os
import unittest
import urllib.request
import logging
import zoneinfo

mock_logger = logging.getLogger("mock")

def datetime_from_iso_format(iso):
    return datetime.fromisoformat(iso).replace(tzinfo=None)

def mock_now_func(timeOfNow):
    return lambda : datetime_from_iso_format(timeOfNow)

def load_test_schedule_json(file):
    current_file_directory = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_file_directory, 'testdata', 'schedules', file)
    with open(file_path, 'r') as file:
        return json.load(file)

class MockResponse:
    def __init__(self, status_code, jsonResponse, textResponse):
        self.status_code = status_code
        self._jsonResponse = jsonResponse
        self.text = textResponse

    def json(self):
        return self._jsonResponse

class MockNetwork:
    def add_json_content_type(self, type):
        return
    
    # This fetch method is a test double that attempts to replicate the behavior
    # of the circuit python portal base fetch method as so we can test out our
    # code in CPython.
    def fetch(self, url, headers = {}, timeout=30):
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req) as response:
                data = response.read()
                text = data.decode('utf-8')
                jsonData = json.loads(text)
                return MockResponse(response.status, jsonData, text)
        except urllib.error.HTTPError as e:
            data = e.read()
            text = data.decode('utf-8')
            jsonData = json.loads(text)
            return MockResponse(e.code, jsonData, text)
    
class Test_next_trains(unittest.TestCase):
    def test_next_trains(self):
        # The goal of this test is to be a system level test that actually calls
        # next_trains to connect together _fetch_schedules_and_predictions and
        # _analyze_data to actually make an HTTP request to MBTA API to make
        # sure we can really analyze that real data.

        # When we provide the timestamp for "now" we will give the timestamp of
        # 1am on the current morning in America/New_York (the MBTA schedule's timezone).
        # We will do this because if the test is running late at night there is a chance
        # that there are no more trains tonight and the test expects that we will get
        # some results back for the train. Setting the time to 1am of today's MBTA schedule
        # ensures we don't filter out trains that have already happened.
        boston_tz = zoneinfo.ZoneInfo("America/New_York")
        now = datetime.now(boston_tz).replace(tzinfo=None)
        mock_now = lambda : now.replace(hour=1, minute=0, second=0, microsecond=0)

        deps = TrainPredictorDependencies(MockNetwork(), datetime, timedelta, mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)
        results = train_predictor.next_trains(count=1)

        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0], None)
        
        # Since we said that we will test as if it is 1am we should be getting
        # the first train of the day. This is ALMOST always an inbound train
        # that happens a 5am. So lets verify it is inbound and happens before 8
        # am.
        self.assertEqual(results[0].direction, Direction.IN_BOUND)

        expected_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        self.assertLess(results[0].time, expected_time)

class Test_fetch_schedules_and_predictions(unittest.TestCase):
    def test_fetch(self):
        # This is a basic test that the train predictor can make a request to
        # the MBTA APIs and get something back. For this test we won't bother
        # doing anything more than having the MockNetwork make the request and
        # do the json decode. If that worked that is good enough for this test.
        # We will use Test_next_trains to connect together testing for
        # _fetch_schedules_and_predictions and _analyze_data to make sure we can
        # actually analyze data that is currently coming out of the API.
        deps = TrainPredictorDependencies(MockNetwork(), datetime=None, timedelta=timedelta, nowFcn=None, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)
        train_predictor._fetch_schedules_and_predictions()
        
    def test_bad_api_key(self):
        # In my original implementation if a bad MBTA API key was provided then
        # _fetch_schedules_and_predictions would just return an empty JSON
        # response that would be interpreted by the rest of the code as there
        # being no trains coming. This resulted in the board being blank.
        # Instead we should throw an error in this case.
        deps = TrainPredictorDependencies(MockNetwork(), datetime=None, timedelta=timedelta, nowFcn=None, mbta_api_key="this_is_a_bad_API_key", logger=mock_logger)
        train_predictor = TrainPredictor(deps)
        with self.assertRaisesRegex(RuntimeError, "Failed to fetch data from MBTA API. status_code: 403 response:"):
            train_predictor._fetch_schedules_and_predictions()

class Test_data_source_url(unittest.TestCase):
    def test_default_stop_url(self):
        deps = TrainPredictorDependencies(network=None, datetime=None, timedelta=timedelta, nowFcn=None, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)
        url = train_predictor._get_data_source_url()
        self.assertIn("filter[stop]=place-FB-0275", url)
        self.assertNotIn("filter[route]", url)

    def test_custom_stop_and_route_url(self):
        deps = TrainPredictorDependencies(network=None, datetime=None, timedelta=timedelta, nowFcn=None, mbta_api_key=None, logger=mock_logger, stop_id="place-davis", route_id="Red")
        train_predictor = TrainPredictor(deps)
        url = train_predictor._get_data_source_url()
        self.assertIn("filter[stop]=place-davis", url)
        self.assertIn("filter[route]=Red", url)

class Test_analyze_data(unittest.TestCase):
    def test_simple_outbound(self):
        # Simple test with best case where we have both the schedule data and
        # prediction data for a train.
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('simple_outbound.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].schedule_id, "schedule-Sept8Read-768162-787-FB-0275-S-130")
        self.assertEqual(result[0].direction, Direction.OUT_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:05:11")

    def test_simple_inbound(self):
        # Simple test with best case where we have both the schedule data and
        # prediction data for a train.
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('simple_inbound.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].schedule_id, "schedule-Sept8Read-768162-787-FB-0275-S-130")
        self.assertEqual(result[0].direction, Direction.IN_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:05:11")

    def test_simple_sparse(self):
        # This is the same as test_simple but uses a sparse dataset. The MBTA
        # allows requesting a more minimal dataset. So this is the smallest
        # amount of data that I think we can get away with requesting at the
        # moment.
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('simple_sparse.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].direction, Direction.OUT_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:05:11")
    
    def test_no_prediction_data_outbound(self):
        # When there is no prediction data in the JSON from the MBTA we should
        # fallback to using the schedule time
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('simple_no_prediction_outbound.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].direction, Direction.OUT_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:06:01")

    def test_no_prediction_data_inbound(self):
        # When there is no prediction data in the JSON from the MBTA we should
        # fallback to using the schedule time
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('simple_no_prediction_inbound.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].direction, Direction.IN_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:06:01")

    def test_no_departure_outbound(self):
        # Simple test with best case where we have both the schedule data and
        # prediction data for a train.
        #
        # If the departure time is null for the prediction we should fall back
        # to using the arrival time of the prediction.
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('simple_no_departure_outbound.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].direction, Direction.OUT_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:04:53")


    def test_no_arrival_inbound(self):
        # Simple test with best case where we have both the schedule data and
        # prediction data for a train.
        #
        # If the arrival time is null for the prediction we should fall back
        # to using the departure time of the prediction.
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('simple_no_arrival_inbound.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].direction, Direction.IN_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:05:11")


    def test_multiple_data_request_one_result(self):
        # There are multiple possible results that could be returned but only
        # one is requested
        mock_now = mock_now_func('2025-10-22T04:06:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('multiple_results.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].direction, Direction.IN_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T05:06:00")

    def test_multiple_data_request_more_results(self):
        # There are two possible results that could be returned but three are
        # requested
        mock_now = mock_now_func('2025-10-22T04:06:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('multiple_results.json')
        
        count = 3
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].direction, Direction.IN_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T05:06:00")
        self.assertEqual(result[1].direction, 0)
        self.assertEqual(result[1].time.isoformat(), "2025-10-22T06:06:00")
        self.assertEqual(result[2], None)

    def old_results_filtered(self):
        # There are multiple possible results that could be returned but only
        # one is requested
        mock_now = mock_now_func('2025-10-22T05:06:20-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps, filterResultsAfterSeconds=10)

        data = load_test_schedule_json('multiple_results.json')
        
        count = 3
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].direction, Direction.OUT_BOUND)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T06:06:00-04:00")
        self.assertEqual(result[1], None)
        self.assertEqual(result[2], None)


    def test_data_array_empty(self):
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('data_array_empty.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], None)

    def test_no_data_property(self):
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('no_data_property.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], None)

    def test_mark_train_arrived(self):
        # If a train is already marked as arrived because the application has
        # already played the train animation for that train then the train
        # predictor should not return that train as an option from _analyze_data. 
        mock_now = mock_now_func('2025-10-22T04:06:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        data = load_test_schedule_json('multiple_results.json')
        
        count = 1
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].schedule_id, "schedule-Sept8Read-768347-704-FB-0275-S-10")

        # Now when we mark the train as arrived we should filter it out of the
        # results and show the next train.
        train_predictor.mark_train_arrived(result[0])

        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertNotEqual(result[0].schedule_id, "schedule-Sept8Read-768347-704-FB-0275-S-10")
        self.assertEqual(result[0].schedule_id, "schedule-Sept8Read-768333-710-FB-0275-S-10")

        # Since IDs are only unique for a day the train predictor needs to have
        # it's cache of arrived trains cleared every night to avoid incorrectly
        # including a train that had the same ID as on a previous day.
        train_predictor.clear_cache()
        result = train_predictor._analyze_data(count, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].schedule_id, "schedule-Sept8Read-768347-704-FB-0275-S-10")

    def test_cache_prediction(self):
        # We cache predictions because as soon as the train leaves the station
        # the prediction is removed from the MBTA API response and we want to
        # make sure we still use the prediction time and not the schedule time.
        mock_now = mock_now_func('2025-10-22T23:04:00-04:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps)

        schedule_id = "schedule-Sept8Read-768162-787-FB-0275-S-130"
        data_with_prediction = load_test_schedule_json('simple_inbound.json')
        data_no_prediction = load_test_schedule_json('simple_no_prediction_inbound.json')
        
        # First the train is far away and we have no prediction
        count = 1
        result = train_predictor._analyze_data(count, data_no_prediction)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].schedule_id, schedule_id)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:06:01")

        # Then the train gets close by and we get a prediction from the MBTA API
        result = train_predictor._analyze_data(count, data_with_prediction)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].schedule_id, schedule_id)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:05:11")

        # Then the train departs the station and the prediction is removed from
        # the MBTA API response. We should use the last predicted time that we
        # cached and not the schedule time.
        result = train_predictor._analyze_data(count, data_no_prediction)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].schedule_id, schedule_id)
        self.assertEqual(result[0].time.isoformat(), "2025-10-22T23:05:11")

class Test_train_passing_warning(unittest.TestCase):
    # For simplicity in these tests we will always use a trainWarningSeconds of one minute and set "now" = 2025-10-22T02:00:00
    def create_predictor(self):
        mock_now = mock_now_func('2025-10-22T02:00:00')
        deps = TrainPredictorDependencies(network=None, datetime=datetime, timedelta=timedelta, nowFcn=mock_now, mbta_api_key=None, logger=mock_logger)
        train_predictor = TrainPredictor(deps, trainWarningSeconds=60)
        return train_predictor

    def test_train_is_far(self):
        # When a train is far away we should not return a warning for the train
        train_predictor = self.create_predictor()
        train = TrainArrival("mockId", datetime_from_iso_format("2025-10-22T03:00:00"), Direction.IN_BOUND)
        warning = train_predictor.train_passing_warning(train)
        self.assertIsNone(warning)

    def test_train_is_close(self):
        # When a train is close we should return a warning for the train
        train_predictor = self.create_predictor()

        monotonic_now = time.monotonic()
        train = TrainArrival("mockId", datetime_from_iso_format("2025-10-22T02:00:30"), Direction.IN_BOUND)
        warning = train_predictor.train_passing_warning(train)
        self.assertIsNotNone(warning)
        self.assertEqual(warning.direction, Direction.IN_BOUND)
        exp_monotonic_time = monotonic_now + 30
        self.assertAlmostEqual(exp_monotonic_time, warning._end_monotonic, delta=1)

    def test_warning_cutoff(self):
        # We should warn when the train departure time is within trainWarningSeconds of now,
        # but not if it has already passed or is further out than trainWarningSeconds.
        train_predictor = self.create_predictor()

        # now is 2025-10-22T02:00:00, trainWarningSeconds = 60.
        # Train departing at 02:00:59 is within 60s -> warning
        train = TrainArrival("mockId", datetime_from_iso_format("2025-10-22T02:00:59"), Direction.IN_BOUND)
        warning = train_predictor.train_passing_warning(train)
        self.assertIsNotNone(warning)

        # Train departing at 02:01:01 is > 60s out -> no warning
        train = TrainArrival("mockId", datetime_from_iso_format("2025-10-22T02:01:01"), Direction.IN_BOUND)
        warning = train_predictor.train_passing_warning(train)
        self.assertIsNone(warning)

        # Train in the past -> no warning
        train = TrainArrival("mockId", datetime_from_iso_format("2025-10-22T01:59:59"), Direction.IN_BOUND)
        warning = train_predictor.train_passing_warning(train)
        self.assertIsNone(warning)

class Test_TrainArrival(unittest.TestCase):
    def test_create_arrival(self):
        arrival = TrainArrival("1234", "mock_time", Direction.IN_BOUND)
        self.assertEqual(arrival.schedule_id, "1234")
        self.assertEqual(arrival.time, "mock_time")
        self.assertEqual(arrival.direction, Direction.IN_BOUND)

    def test_sort_by_time(self):
        trains = [
            TrainArrival("0", datetime_from_iso_format("2025-10-22T05:00:00"), Direction.IN_BOUND),
            TrainArrival("1", datetime_from_iso_format("2025-10-22T01:00:00"), Direction.IN_BOUND),
            TrainArrival("2", datetime_from_iso_format("2025-10-22T03:00:00"), Direction.IN_BOUND),
            TrainArrival("3", datetime_from_iso_format("2025-10-22T02:00:00"), Direction.IN_BOUND),
            TrainArrival("4", datetime_from_iso_format("2025-10-22T04:00:00"), Direction.IN_BOUND),
        ]

        trains.sort(key=TrainArrival.sort_by_time)

        self.assertEqual(trains[0].schedule_id, "1")
        self.assertEqual(trains[1].schedule_id, "3")
        self.assertEqual(trains[2].schedule_id, "2")
        self.assertEqual(trains[3].schedule_id, "4")
        self.assertEqual(trains[4].schedule_id, "0")

class Test_TrainWarning(unittest.TestCase):
    def test_create_warning(self):
        warning = TrainWarning(0, Direction.IN_BOUND)
        self.assertEqual(warning.direction, Direction.IN_BOUND)

    def test_should_stop(self):
        warning = TrainWarning(time.monotonic() + 1, Direction.IN_BOUND)
        self.assertFalse(warning.should_stop())

        time.sleep(2)

        self.assertTrue(warning.should_stop())

if __name__ == '__main__':
    unittest.main()