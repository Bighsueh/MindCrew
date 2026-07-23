"""Facilitator-paced progression (Spec 04-06 §5.8 / v4.15).

取代 crew advance vote：由 ``progression_watcher`` 決定性推進 micro 內的細格
sub_phase（readiness / time-box / time-floor）並保證白話交代；micro / macro
邊界仍由 Evaluator 驅動（加最後一格 guard）。
"""
