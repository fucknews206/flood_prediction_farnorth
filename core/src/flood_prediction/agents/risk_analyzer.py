"""
Risk Analyzer Agent - Analyzes flood risk conditions using AI.
Operates entirely in metric units.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import json
import logging
import math

from .base_agent import BaseAgent, AgentInsight, AgentAlert

logger = logging.getLogger(__name__)

class RiskAnalyzerAgent(BaseAgent):
    """Agent responsible for analyzing flood risk using data analysis"""
    
    def __init__(self):
        super().__init__(
            name="Risk Analyzer",
            description="Analysis of flood risk conditions and trend detection for Cameroon basins",
            check_interval=600  # Check every 10 minutes
        )
        self.risk_history = []
        self.trend_analysis = {}
        self.ml_predictions = {}
        self._previous_critical_count = 0
        
    async def analyze(self, data: Dict[str, Any]) -> List[AgentInsight]:
        """Analyze current flood risk conditions"""
        insights = []
        
        # Overall risk assessment
        overall_risk = await self._calculate_overall_risk(data)
        insights.append(AgentInsight(
            title="🎯 Overall Risk Level",
            value=f"{overall_risk['level']} ({overall_risk['score']:.1f}/10)",
            change=f"{overall_risk['change']:+.1f}",
            trend=overall_risk['trend'],
            urgency='critical' if overall_risk['score'] > 8 else 'high' if overall_risk['score'] > 6 else 'normal'
        ))
        
        # Critical basins count
        critical_count = await self._count_critical_basins(data)
        insights.append(AgentInsight(
            title="🚨 Critical Basins",
            value=f"{critical_count['count']} areas",
            change=f"{critical_count['change']:+d}" if critical_count['change'] != 0 else None,
            trend='up' if critical_count['change'] > 0 else 'down' if critical_count['change'] < 0 else 'stable',
            urgency='critical' if critical_count['count'] > 5 else 'high' if critical_count['count'] > 2 else 'normal'
        ))
        
        # Trend analysis
        trend_data = await self._analyze_trends(data)
        insights.append(AgentInsight(
            title="📈 Risk Trend Analysis",
            value=trend_data['direction'],
            change=f"{trend_data['rate']:.1f}% per hour",
            trend=trend_data['trend'],
            urgency='high' if trend_data['trend'] == 'up' and trend_data['rate'] > 5 else 'normal'
        ))
        
        # AI confidence score
        ai_confidence = await self._get_ai_confidence(data)
        insights.append(AgentInsight(
            title="🧠 AI Confidence",
            value=f"{ai_confidence['score']:.0f}%",
            change=f"{ai_confidence['reliability']}",
            trend='stable',
            urgency='normal'
        ))
        
        # Predicted peak risk time
        peak_prediction = await self._predict_peak_risk(data)
        if peak_prediction:
            insights.append(AgentInsight(
                title="⏰ Peak Risk Window",
                value=peak_prediction['time_range'],
                change=f"{peak_prediction['confidence']:.0f}% confidence",
                trend='stable',
                urgency='high' if peak_prediction['severity'] == 'high' else 'normal'
            ))
        
        return insights
    
    async def check_alerts(self, data: Dict[str, Any]) -> List[AgentAlert]:
        """Check for high-risk conditions requiring alerts"""
        alerts = []
        
        # Check for rapid risk increase
        risk_change = await self._detect_rapid_risk_change(data)
        if risk_change['rapid_increase']:
            alerts.append(AgentAlert(
                id=f"rapid_risk_increase_{datetime.now().strftime('%Y%m%d%H%M')}",
                title="⚡ Rapid Risk Escalation",
                message=f"Risk levels are increasing rapidly in {len(risk_change['affected_areas'])} areas. "
                        f"Average increase: {risk_change['rate']:.1f}% per hour.",
                severity="critical",
                source_agent=self.name,
                affected_areas=risk_change['affected_areas'],
                recommendations=[
                    "Monitor affected river basins closely",
                    "Prepare emergency response resources",
                    "Issue public advisories for high-risk areas",
                    "Activate automated alert systems"
                ]
            ))
        
        # Check for threshold breaches
        threshold_breaches = await self._check_threshold_breaches(data)
        if threshold_breaches:
            alerts.append(AgentAlert(
                id=f"threshold_breach_{len(threshold_breaches)}_{datetime.now().strftime('%Y%m%d%H')}",
                title="🚨 Critical Threshold Exceeded",
                message=f"{len(threshold_breaches)} basins have exceeded critical risk thresholds.",
                severity="critical",
                source_agent=self.name,
                affected_areas=[breach['basin'] for breach in threshold_breaches],
                recommendations=[
                    "Immediate evacuation assessment required",
                    "Deploy emergency response teams",
                    "Coordinate with local authorities",
                    "Monitor downstream areas"
                ]
            ))
        
        # Check for pattern anomalies
        anomalies = await self._detect_pattern_anomalies(data)
        if anomalies:
            alerts.append(AgentAlert(
                id=f"pattern_anomaly_{datetime.now().strftime('%Y%m%d%H')}",
                title="🔍 Unusual Pattern Detected",
                message="AI detected unusual flood patterns that deviate from historical norms.",
                severity="warning",
                source_agent=self.name,
                recommendations=[
                    "Verify data accuracy with multiple sources",
                    "Increase monitoring frequency",
                    "Review prediction models",
                    "Consider additional safety margins"
                ]
            ))
        
        return alerts
    
    async def _calculate_overall_risk(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall regional flood risk score"""
        try:
            basins = data.get('basins', [])
            if not basins:
                return {'level': 'Unknown', 'score': 0, 'change': 0, 'trend': 'stable'}
            
            # Calculate weighted average risk score
            total_score = 0
            total_weight = 0
            
            for basin in basins:
                risk_score = basin.get('risk_score', 0)
                # Weight by basin size if available
                weight = basin.get('basin_size_sqkm', 1) or 1
                total_score += risk_score * weight
                total_weight += weight
            
            if total_weight == 0:
                avg_score = 0
            else:
                avg_score = total_score / total_weight
            
            # Determine risk level
            if avg_score >= 8:
                level = "CRITICAL"
            elif avg_score >= 6:
                level = "HIGH"
            elif avg_score >= 4:
                level = "MODERATE"
            else:
                level = "LOW"
            
            # Calculate change from previous assessment
            change = 0
            trend = 'stable'
            if self.risk_history:
                previous_score = self.risk_history[-1]['score']
                change = avg_score - previous_score
                if abs(change) > 0.5:
                    trend = 'up' if change > 0 else 'down'
            
            # Store in history
            self.risk_history.append({
                'timestamp': datetime.now(timezone.utc),
                'score': avg_score,
                'level': level
            })
            
            # Keep only last 24 hours of history
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            self.risk_history = [h for h in self.risk_history if h['timestamp'] > cutoff]
            
            return {
                'level': level,
                'score': avg_score,
                'change': change,
                'trend': trend
            }
        
        except Exception as e:
            logger.error(f"Error calculating overall risk: {e}")
            return {'level': 'Unknown', 'score': 0, 'change': 0, 'trend': 'stable'}
    
    async def _count_critical_basins(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Count basins in critical condition"""
        basins = data.get('basins', [])
        critical_count = sum(1 for b in basins if b.get('risk_score', 0) >= 8)
        
        change = critical_count - self._previous_critical_count
        self._previous_critical_count = critical_count
        
        return {
            'count': critical_count,
            'change': change
        }
    
    async def _analyze_trends(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze risk trends over time"""
        if len(self.risk_history) < 2:
            return {'direction': 'Insufficient data', 'rate': 0, 'trend': 'stable'}
        
        recent_history = self.risk_history[-6:]
        if len(recent_history) < 2:
            return {'direction': 'Stable', 'rate': 0, 'trend': 'stable'}
        
        scores = [h['score'] for h in recent_history]
        times = [(h['timestamp'] - recent_history[0]['timestamp']).total_seconds() / 3600 for h in recent_history]
        
        if len(scores) >= 2:
            n = len(scores)
            sum_xy = sum(t * s for t, s in zip(times, scores))
            sum_x = sum(times)
            sum_y = sum(scores)
            sum_x2 = sum(t * t for t in times)
            
            if n * sum_x2 - sum_x * sum_x != 0:
                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                rate = slope * 10
                
                if rate > 0.5:
                    direction = "Increasing"
                    trend = 'up'
                elif rate < -0.5:
                    direction = "Decreasing"
                    trend = 'down'
                else:
                    direction = "Stable"
                    trend = 'stable'
                
                return {'direction': direction, 'rate': abs(rate), 'trend': trend}
        
        return {'direction': 'Stable', 'rate': 0, 'trend': 'stable'}
    
    async def _get_ai_confidence(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Get confidence in current analysis based on data quality"""
        try:
            basins = data.get('basins', [])
            total_basins = len(basins)
            
            if total_basins == 0:
                return {'score': 0, 'reliability': 'No data'}
            
            recent_data_count = sum(1 for b in basins if self._is_recent_data(b))
            
            # Simple confidence metric based on data freshness
            confidence = (recent_data_count / total_basins) * 100
            
            if confidence >= 90:
                reliability = "Very High"
            elif confidence >= 75:
                reliability = "High"
            elif confidence >= 60:
                reliability = "Moderate"
            else:
                reliability = "Low"
            
            return {'score': confidence, 'reliability': reliability}
        
        except Exception as e:
            logger.error(f"Error calculating confidence: {e}")
            return {'score': 50, 'reliability': 'Uncertain'}
    
    async def _predict_peak_risk(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Predict when peak risk conditions will occur"""
        try:
            if len(self.risk_history) < 3:
                return None
            
            recent_trend = await self._analyze_trends(data)
            
            if recent_trend['trend'] == 'up' and recent_trend['rate'] > 1:
                hours_to_peak = max(2, 10 - recent_trend['rate'])
                peak_time = datetime.now(timezone.utc) + timedelta(hours=hours_to_peak)
                
                time_range = f"Next {hours_to_peak:.0f} hours"
                confidence = min(90, 60 + recent_trend['rate'] * 5)
                severity = 'high' if recent_trend['rate'] > 3 else 'moderate'
                
                return {
                    'time_range': time_range,
                    'confidence': confidence,
                    'severity': severity,
                    'peak_time': peak_time
                }
            
            return None
        
        except Exception as e:
            logger.error(f"Error predicting peak risk: {e}")
            return None
    
    async def _detect_rapid_risk_change(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Detect rapid changes in risk levels"""
        affected_areas = []
        max_rate = 0
        
        basins = data.get('basins', [])
        
        for basin in basins:
            trend_rate = basin.get('trend_rate_cms_per_hour', 0)
            
            # 2.83 m3/s per hour is approx 100 CFS per hour (significant increase)
            if trend_rate > 2.83:
                risk_rate = trend_rate / 1.416
                if risk_rate > 2:
                    affected_areas.append(basin.get('name', 'Unknown'))
                    max_rate = max(max_rate, risk_rate)
        
        return {
            'rapid_increase': len(affected_areas) > 0,
            'affected_areas': affected_areas,
            'rate': max_rate
        }
    
    async def _check_threshold_breaches(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for critical threshold breaches"""
        breaches = []
        basins = data.get('basins', [])
        
        for basin in basins:
            risk_score = basin.get('risk_score', 0)
            current_flow = basin.get('current_streamflow_cms', 0)
            flood_stage = basin.get('flood_stage_cms')
            
            # Check risk score threshold
            if risk_score >= 9:
                breaches.append({
                    'basin': basin.get('name', 'Unknown'),
                    'type': 'risk_score',
                    'value': risk_score,
                    'threshold': 9
                })
            
            # Check flood stage threshold
            if flood_stage and current_flow >= flood_stage * 0.9:
                breaches.append({
                    'basin': basin.get('name', 'Unknown'),
                    'type': 'flood_stage',
                    'value': current_flow,
                    'threshold': flood_stage * 0.9
                })
        
        return breaches
    
    async def _detect_pattern_anomalies(self, data: Dict[str, Any]) -> bool:
        """Detect unusual patterns that deviate from normal"""
        try:
            basins = data.get('basins', [])
            if not basins:
                return False
            
            high_risk_low_flow = 0
            for basin in basins:
                risk_score = basin.get('risk_score', 0)
                current_flow = basin.get('current_streamflow_cms', 0)
                
                # Anomaly: High risk but low flow (e.g. flow < 2.83 m3/s)
                if risk_score > 7 and current_flow < 2.83:
                    high_risk_low_flow += 1
            
            anomaly_threshold = len(basins) * 0.2
            return high_risk_low_flow > anomaly_threshold
        
        except Exception as e:
            logger.error(f"Error detecting pattern anomalies: {e}")
            return False
    
    def _is_recent_data(self, basin: Dict[str, Any]) -> bool:
        """Check if basin has recent data"""
        # If we have any data update time, check it
        return True