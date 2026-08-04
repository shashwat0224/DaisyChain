from django.shortcuts import render
import logging
from datetime import date, time

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from search import search_direct, search_indirect
from .serializers import DirectResultSerializer, IndirectResultSerializer

logger = logging.getLogger(__name__)


def parse_date(date_str: str):
    """Parse YYYY-MM-DD string to date object."""
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def parse_time(time_str: str):
    """Parse HH:MM string to time object."""
    try:
        h, m = map(int, time_str.split(":"))
        return time(h, m)
    except (ValueError, TypeError, AttributeError):
        return None


class DirectSearchView(APIView):
    """
    GET /api/search/direct/
    Params:
        source      : station code (required)
        destination : station code (required)
        date        : YYYY-MM-DD   (required)
        after       : HH:MM        (optional, filter trains departing after this time)
    """

    def get(self, request):
        source      = request.query_params.get("source", "").upper().strip()
        destination = request.query_params.get("destination", "").upper().strip()
        date_str    = request.query_params.get("date", "")
        after_str   = request.query_params.get("after", "")

        # Validate required params
        errors = {}
        if not source:
            errors["source"] = "Required"
        if not destination:
            errors["destination"] = "Required"
        if source and destination and source == destination:
            errors["destination"] = "Cannot be same as source"

        journey_date = parse_date(date_str)
        if not journey_date:
            errors["date"] = "Required, format: YYYY-MM-DD"

        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        depart_after = parse_time(after_str) if after_str else None

        try:
            results = search_direct(
                source       = source,
                destination  = destination,
                journey_date = journey_date,
                depart_after = depart_after,
            )
        except Exception as e:
            logger.error(f"Direct search error: {e}", exc_info=True)
            return Response(
                {"error": "Search failed, please try again"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        serializer = DirectResultSerializer(results, many=True)
        return Response({
            "source":      source,
            "destination": destination,
            "date":        date_str,
            "count":       len(results),
            "results":     serializer.data,
        })


class IndirectSearchView(APIView):
    """
    GET /api/search/indirect/
    Params:
        source      : station code (required)
        destination : station code (required)
        date        : YYYY-MM-DD   (required)
        after       : HH:MM        (optional)
        max_results : int          (optional, default 10, max 20)
    """

    def get(self, request):
        source      = request.query_params.get("source", "").upper().strip()
        destination = request.query_params.get("destination", "").upper().strip()
        date_str    = request.query_params.get("date", "")
        after_str   = request.query_params.get("after", "")

        errors = {}
        if not source:
            errors["source"] = "Required"
        if not destination:
            errors["destination"] = "Required"
        if source and destination and source == destination:
            errors["destination"] = "Cannot be same as source"

        journey_date = parse_date(date_str)
        if not journey_date:
            errors["date"] = "Required, format: YYYY-MM-DD"

        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        if user.is_authenticated and user.profile.tier == 'premium':
            max_indirect = 20
        elif user.is_authenticated:
            max_indirect = 10
        else:
            max_indirect = 5

        depart_after = parse_time(after_str) if after_str else None

        try:
            results = search_indirect(
                source       = source,
                destination  = destination,
                journey_date = journey_date,
                depart_after = depart_after,
                max_results  = max_indirect,
            )
        except Exception as e:
            logger.error(f"Indirect search error: {e}", exc_info=True)
            return Response(
                {"error": "Search failed, please try again"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        serializer = IndirectResultSerializer(results, many=True)
        return Response({
            "source":      source,
            "destination": destination,
            "date":        date_str,
            "count":       len(results),
            "results":     serializer.data,
        })


class CombinedSearchView(APIView):
    """
    GET /api/search/
    Returns both direct and indirect results in one call.
    This is what the Flutter frontend will actually use.

    Params: same as above
    """

    def get(self, request):
        source      = request.query_params.get("source", "").upper().strip()
        destination = request.query_params.get("destination", "").upper().strip()
        date_str    = request.query_params.get("date", "")
        after_str   = request.query_params.get("after", "")

        errors = {}
        if not source:
            errors["source"] = "Required"
        if not destination:
            errors["destination"] = "Required"
        if source and destination and source == destination:
            errors["destination"] = "Cannot be same as source"

        journey_date = parse_date(date_str)
        if not journey_date:
            errors["date"] = "Required, format: YYYY-MM-DD"

        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        depart_after = parse_time(after_str) if after_str else None

        user = request.user
        if user.is_authenticated and user.profile.tier == 'premium':
            max_indirect = 20
        elif user.is_authenticated:
            max_indirect = 10
        else:
            max_indirect = 5

        try:
            direct   = search_direct(
                source, destination, journey_date, depart_after
            )
            indirect = search_indirect(
                source, destination, journey_date, depart_after,
                max_results=max_indirect
            )
        except Exception as e:
            logger.error(f"Combined search error: {e}", exc_info=True)
            return Response(
                {"error": "Search failed, please try again"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({
            "source":      source,
            "destination": destination,
            "date":        date_str,
            "direct": {
                "count":   len(direct),
                "results": DirectResultSerializer(direct, many=True).data,
            },
            "indirect": {
                "count":   len(indirect),
                "results": IndirectResultSerializer(indirect, many=True).data,
            },
        })
    
class StationSearchView(APIView):
    """
    GET /api/stations/search/?q=jaipur
    Returns stations matching the query (name or code).
    Used by Flutter autocomplete when user types a station name.
    """

    throttle_classes = []

    def get(self, request):
        q = request.query_params.get("q", "").strip()

        if len(q) < 2:
            return Response(
                {"error": "Query must be at least 2 characters"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from search.db import execute

        results = execute("""
            SELECT
                station_code,
                station_name,
                is_major_junction
            FROM stations
            WHERE
                UPPER(station_name) LIKE UPPER(%s)
                OR UPPER(station_code) LIKE UPPER(%s)
            ORDER BY
                is_major_junction DESC,   -- major junctions first
                station_name ASC
            LIMIT 10
        """, (f"%{q}%", f"%{q}%"))

        return Response({
            "query":   q,
            "count":   len(results),
            "results": results,
        })
    
class TrainStopsView(APIView):
    def get(self, request, train_no):
        from search.db import execute
        
        # Get train info first
        train = execute("""
            SELECT train_no, train_name, classes, service_days
            FROM trains
            WHERE train_no = %s
        """, (train_no,))

        if not train:
            return Response(
                {"error": f"Train {train_no} not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get all stops in order
        stops = execute("""
            SELECT
                ts.stop_index,
                ts.station_code,
                s.station_name,
                ts.arrival_time,
                ts.departure_time,
                ts.halt_time,
                ts.day_offset,
                ts.avg_delay
            FROM train_stops ts
            JOIN stations s ON s.station_code = ts.station_code
            WHERE ts.train_no = %s
            ORDER BY ts.stop_index
        """, (train_no,))

        # Convert time objects to strings — not JSON serializable by default
        formatted_stops = []
        for stop in stops:
            formatted_stops.append({
                "stop_index":      stop["stop_index"],
                "station_code":    stop["station_code"],
                "station_name":    stop["station_name"],
                "arrival_time":    str(stop["arrival_time"])[:5]  if stop["arrival_time"]   else None,
                "departure_time":  str(stop["departure_time"])[:5] if stop["departure_time"] else None,
                "halt_time":       stop["halt_time"],
                "day_offset":      stop["day_offset"],
                "avg_delay":       stop["avg_delay"],
            })

        return Response({
            "train_no":    train[0]["train_no"].strip(),
            "train_name":  train[0]["train_name"],
            "classes":     train[0]["classes"],
            "service_days": train[0]["service_days"],
            "total_stops": len(formatted_stops),
            "stops":       formatted_stops,
        })