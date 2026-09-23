#small pcbnew helpers shared by the checks: units, design rules and zone filling
import pcbnew

MM, TOMM = pcbnew.FromMM, pcbnew.ToMM
TRACK_W = 0.1016            #4 mil, JLCPCB's free-tier minimum
CLEAR = 0.1016
VIA_D, VIA_DRILL = 0.60, 0.30


#rebuild connectivity, then fill every zone
def fill(board):
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


#apply the board's design rules (JLCPCB 6-layer, 4 mil)
def set_rules(board):
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = MM(TRACK_W)
    ds.m_ViasMinSize = MM(0.45)
    ds.m_MinThroughDrill = MM(0.20)
    ds.m_CopperEdgeClearance = MM(0.3)
    ds.m_MinClearance = MM(CLEAR)
    ds.m_HoleClearance = MM(0.20)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(MM(CLEAR))
    nc.SetTrackWidth(MM(TRACK_W))
    nc.SetViaDiameter(MM(VIA_D))
    nc.SetViaDrill(MM(VIA_DRILL))
    ds.m_MinResolvedSpokes = 1
    ds.SetCopperLayerCount(6)


#area of a polygon given as [(x, y), ...]
def area(p):
    a = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2
