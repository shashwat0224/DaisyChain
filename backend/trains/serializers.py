from rest_framework import serializers


class DirectResultSerializer(serializers.Serializer):
    train_no         = serializers.CharField()
    train_name       = serializers.CharField()
    source_station   = serializers.CharField()
    dest_station     = serializers.CharField()
    departure_time   = serializers.TimeField(format="%H:%M")
    departure_day    = serializers.IntegerField()
    arrival_time     = serializers.TimeField(format="%H:%M")
    arrival_day      = serializers.IntegerField()
    journey_minutes  = serializers.IntegerField()
    journey_duration = serializers.CharField(source='journey_duration_str')
    stops_in_between = serializers.IntegerField()
    classes          = serializers.CharField()
    service_days     = serializers.CharField()


class TransferSerializer(serializers.Serializer):
    station_code = serializers.CharField()
    station_name = serializers.CharField()
    is_major     = serializers.BooleanField()
    wait_minutes = serializers.IntegerField()
    arrive_time  = serializers.TimeField(format="%H:%M")
    arrive_day   = serializers.IntegerField()
    depart_time  = serializers.TimeField(format="%H:%M")
    depart_day   = serializers.IntegerField()


class IndirectResultSerializer(serializers.Serializer):
    leg1              = DirectResultSerializer()
    leg2              = DirectResultSerializer()
    transfer          = TransferSerializer()
    total_minutes     = serializers.IntegerField()
    total_duration    = serializers.CharField(source='total_duration_str')
    is_major_junction = serializers.BooleanField()