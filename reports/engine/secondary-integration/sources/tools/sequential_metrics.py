"""Classify recorded discharges by the controller mode at the actual event."""
def sequential_metrics(events):
 full=[e for e in events if e.get('sync_status')==2 and e.get('ignition_cycle_deg')==720]
 return dict(raw_exhaust_stroke_discharges=sum(abs(e['phase_error_deg'])>180 for e in events),
             wasted_fallback_discharges=sum(e.get('sync_status')==1 and e.get('ignition_cycle_deg')==360 for e in events),
             unsynced_discharges=sum(e.get('sync_status')==0 for e in events),
             unsynced_720_discharges=sum(e.get('sync_status')==0 and e.get('ignition_cycle_deg')==720 for e in events),
             wrong_stroke_sparks=sum(abs(e['phase_error_deg'])>180 for e in full),
             max_spark_720_error_deg=max((abs(e['phase_error_deg']) for e in full if e['rpm']>=50),default=0))
