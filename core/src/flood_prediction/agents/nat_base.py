#!/usr/bin/env python3
import asyncio
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from nat.runtime.loader import load_workflow
    NAT_AVAILABLE = True
    logger.info("NVIDIA NAT runtime available")
except ImportError:
    logger.error("NVIDIA NAT not available. Install with: pip install nvidia-nat")
    NAT_AVAILABLE = False

class FloodPredictionRunner:
    """Unified runner for flood prediction agent workflows"""
    
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent / "nat"
        self.available_agents = {
            'data_collector': 'data_collector_config.yml',
            'risk_analyzer': 'risk_analyzer_config.yml', 
            'emergency_responder': 'emergency_responder_config.yml',
            'predictor': 'predictor_config.yml',
            'h2ogpte_agent': 'h2ogpte_agent_config.yml'
        }
        
    async def run_workflow(self, config_path: str, input_text: str) -> Dict[str, Any]:
        """Run NAT workflow with specified config and input"""
        if not NAT_AVAILABLE:
            return {
                "error": "NVIDIA NAT is not installed in the backend environment. Use Normal Chat or install the NAT dependencies.",
                "status": "error"
            }

        if not Path(config_path).is_file():
            return {"error": f"NAT workflow configuration was not found: {config_path}", "status": "error"}
        
        try:
            logger.info(f"Loading workflow from: {config_path}")
            async with load_workflow(config_path) as workflow:
                logger.info("Executing workflow...")
                async with workflow.run(input_text) as runner:
                    result = await runner.result(to_type=str)
                    
                    # Try to parse as JSON
                    try:
                        parsed_result = json.loads(result)
                        logger.info("Workflow completed successfully")
                        return parsed_result
                    except json.JSONDecodeError:
                        logger.info("Workflow completed with text output")
                        return {"output": result, "status": "success"}
                        
        except Exception as e:
            logger.error(f"NAT workflow execution failed: {e}")
            return {"error": str(e), "status": "error"}

    async def run_data_collector(self, custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Run Data Collector Agent workflow"""
        config_file = self.base_path / self.available_agents['data_collector']
        
        prompt = custom_prompt or """
        You are a Data Collector Agent for Cameroon Far North flood prediction.
        Use only get_far_north_* tools. Resolve a named Far North locality or
        division through the real gazetteer/risk engine before answering.
        Never invent rainfall, river stage, discharge, population, coordinates,
        or substitute Douala, Yaoundé, Garoua, USGS, or NWS values.
        
        Provide a comprehensive status report including:
        - Data freshness and quality metrics
        - API connectivity status
        - Any alerts or issues detected
        - Recommendations for data collection improvement
        
        Return results in JSON format with clear status indicators.
        """
        
        logger.info("Running Data Collector Agent workflow...")
        return await self.run_workflow(str(config_file), prompt)

    async def run_risk_analyzer(self, location: str = "Cameroon", custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Run Risk Analyzer Agent workflow"""
        config_file = self.base_path / self.available_agents['risk_analyzer']
        
        prompt = custom_prompt or f"""
        You are a Risk Analyzer Agent for flood prediction. Analyze flood risk for {location}:
        
        1. Use get_far_north_locality_risk_tool for a named locality
        2. Use get_far_north_division_risk_tool for a named division
        3. Use get_far_north_locality_forecast_tool for a dated forecast question
        4. Use get_far_north_top_risk_localities_tool for ranking questions
        Never invent numeric inputs or call generic/template risk calculators.
        
        Provide detailed analysis including:
        - Overall risk level and score
        - Critical watersheds and risk factors
        - Trend analysis and predictions
        - Immediate vs. long-term risk assessment
        - Specific recommendations for risk mitigation
        
        Focus on actionable intelligence with confidence levels.
        For open-ended future-risk questions, use the real get_far_north_top_risk_localities_tool
        and then get_far_north_locality_forecast_tool only for a covered locality. If the
        forecast result says not_available or has no upstream-basin coverage, say that plainly;
        do not present static susceptibility as a 2-3 day forecast and do not return only a
        hardcoded city name.
        """
        
        logger.info(f"Running Risk Analyzer Agent workflow for {location}...")
        return await self.run_workflow(str(config_file), prompt)

    async def run_emergency_responder(self, scenario: str = "routine_check", custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Run Emergency Responder Agent workflow"""
        config_file = self.base_path / self.available_agents['emergency_responder']
        
        if custom_prompt:
            prompt = custom_prompt
        elif scenario == "flash_flood_alert":
            prompt = """
            EMERGENCY SCENARIO: assess a reported Far North Cameroon flood concern.
            Use only the real get_far_north_locality_risk_tool,
            get_far_north_locality_forecast_tool, or
            get_far_north_division_risk_tool when a named place is supplied.
            Do not invent affected populations, alert status, river measurements,
            or evacuation zones. If no named Far North place or live tool result
            is available, say so and give general safety guidance only. Advise
            users to follow official local emergency instructions.
            """
        else:
            prompt = """
            You are an Emergency Responder Agent for Cameroon Far North.
            Use only the real Far North risk, forecast, and division tools when
            the request identifies a place. Never fabricate incident counts,
            population figures, alert levels, river data, or response resources.
            For general preparedness questions, provide safety guidance and
            clearly distinguish it from live backend data.
            """
        
        logger.info(f"Running Emergency Responder Agent workflow - scenario: {scenario}...")
        return await self.run_workflow(str(config_file), prompt)

    async def run_predictor(self, forecast_hours: int = 24, location: str = "Cameroon", custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Run AI Predictor Agent workflow"""
        config_file = self.base_path / self.available_agents['predictor']
        
        prompt = custom_prompt or f"""
        You are an AI Predictor Agent for flood forecasting. Generate predictions for {location}:
        
            1. Use get_far_north_locality_forecast_tool for the real forecast trajectory
            2. Use get_far_north_top_risk_localities_tool only for a static ranking
            3. Never invent a forecast, discharge, rainfall, or substitute locality
        
        Provide detailed forecast including:
        - Watershed-specific predictions with confidence levels
        - Critical time windows and peak risk periods
        - Model accuracy and reliability assessment
        - Uncertainty ranges and validation recommendations
        - Potential model conflicts or limitations
        
        Emphasize actionable predictive intelligence with clear confidence indicators.
        """
        
        logger.info(f"Running AI Predictor Agent workflow - {forecast_hours}h forecast for {location}...")
        return await self.run_workflow(str(config_file), prompt)

    async def run_h2ogpte_agent(self, task_type: str = "train_model", user_query: str = "", custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Run H2OGPTE ML Agent workflow"""
        config_file = self.base_path / self.available_agents['h2ogpte_agent']
        
        if custom_prompt:
            prompt = custom_prompt
        elif task_type == "train_model":
            prompt = f"""
            As an H2OGPTE ML Agent, help with flood prediction model training using Driverless AI capabilities.
            
            User Request: {user_query}
            
            Please provide comprehensive guidance on:
            1. Explain that no training tool is exposed to this agent at runtime
            2. Analyze dataset requirements and preprocessing needs
            3. Recommend feature engineering strategies for flood prediction
            4. Suggest optimal model architectures and hyperparameters
            5. Provide validation and evaluation strategies
            
            Focus on:
            - Time-series aspects of flood prediction
            - Handling imbalanced flood event data
            - Real-time prediction requirements
            - Model interpretability for emergency response
            - Integration with existing flood monitoring systems
            
            Provide detailed, actionable recommendations with implementation guidance.
            """
        elif task_type == "analyze_performance":
            prompt = f"""
            As an H2OGPTE ML Agent, analyze flood prediction model performance.
            
            User Request: {user_query}
            
            Tasks:
            1. Explain that model-performance tools are not exposed to this agent at runtime
            2. Assess model accuracy, precision, recall for flood prediction
            3. Analyze feature importance and model interpretability
            4. Identify potential improvements and optimization opportunities
            5. Check for model bias and fairness issues
            
            Provide comprehensive analysis with specific recommendations for improvement.
            """
        elif task_type == "optimize_features":
            prompt = f"""
            As an H2OGPTE ML Agent, optimize features for flood prediction models.
            
            User Request: {user_query}
            
            Tasks:
            1. Explain that feature-optimization tools are not exposed to this agent at runtime
            2. Create time-series features (lags, rolling statistics, seasonality)
            3. Design interaction features between environmental variables
            4. Optimize feature selection and dimensionality reduction
            5. Handle missing data and outliers appropriately
            
            Focus on flood prediction specific feature engineering strategies.
            """
        else:
            prompt = f"""
            As an H2OGPTE ML Agent, provide general ML assistance for flood prediction.
            
            User Request: {user_query}
            
            No H2OGPTE flood-data or model-management tools are exposed to this
            agent at runtime. Provide general methodological guidance only; never
            fabricate a model result, flood measurement, locality, or forecast.
            
            Provide expert guidance on ML aspects of flood prediction systems.
            """
        
        logger.info(f"Running H2OGPTE ML Agent workflow - task: {task_type}...")
        return await self.run_workflow(str(config_file), prompt)

    async def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run comprehensive analysis using all agents"""
        logger.info("Running comprehensive flood prediction analysis with all agents...")
        
        results = {}
        
        # Run each agent workflow
        try:
            logger.info("Step 1/5: Data Collection Analysis...")
            results['data_collector'] = await self.run_data_collector()
            
            logger.info("Step 2/5: Risk Analysis...")
            results['risk_analyzer'] = await self.run_risk_analyzer()
            
            logger.info("Step 3/5: Emergency Response Assessment...")
            results['emergency_responder'] = await self.run_emergency_responder()
            
            logger.info("Step 4/5: Predictive Analysis...")
            results['predictor'] = await self.run_predictor()
            
            logger.info("Step 5/5: ML Model Analysis...")
            results['h2ogpte_agent'] = await self.run_h2ogpte_agent('analyze_performance', 'Analyze current flood prediction models')
            
            # Generate summary
            results['comprehensive_summary'] = {
                "analysis_timestamp": asyncio.get_event_loop().time(),
                "total_agents": len(self.available_agents),
                "successful_workflows": sum(1 for r in results.values() if isinstance(r, dict) and r.get('status') != 'error'),
                "overall_status": "completed",
                "recommendations": [
                    "Monitor data collection quality continuously",
                    "Focus on high-risk watersheds identified",
                    "Maintain emergency response readiness",
                    "Validate predictions with multiple sources"
                ]
            }
            
            logger.info("Comprehensive analysis completed successfully")
            return results
            
        except Exception as e:
            logger.error(f"Error in comprehensive analysis: {e}")
            results['error'] = str(e)
            results['status'] = 'partial_failure'
            return results

    def list_available_agents(self) -> Dict[str, Any]:
        """List all available agent configurations"""
        missing_configs = [
            filename for filename in self.available_agents.values()
            if not (self.base_path / filename).is_file()
        ]
        nat_ready = NAT_AVAILABLE and not missing_configs
        return {
            "available_agents": self.available_agents,
            "base_path": str(self.base_path),
            "nat_available": nat_ready,
            "unavailable_reason": (
                None if nat_ready else
                ("NVIDIA NAT is not installed in the backend environment" if not NAT_AVAILABLE
                 else f"Missing NAT workflow files: {', '.join(missing_configs)}")
            ),
            "description": {
                "data_collector": "Collects real-time data from USGS, NOAA, and weather APIs",
                "risk_analyzer": "AI-powered flood risk assessment and analysis", 
                "emergency_responder": "Emergency response coordination and alert management",
                "predictor": "Advanced AI forecasting and predictive analysis",
                "h2ogpte_agent": "AutoML agent for training flood prediction models using H2OGPTE and Driverless AI"
            }
        }

async def main():
    """Main entry point with command-line interface"""
    parser = argparse.ArgumentParser(description="NAT Base Runner for Flood Prediction Agents")
    parser.add_argument('--agent', choices=['data_collector', 'risk_analyzer', 'emergency_responder', 'predictor', 'h2ogpte_agent', 'all'],
                       default='all', help='Agent to run (default: all)')
    parser.add_argument('--prompt', type=str, help='Custom prompt for agent')
    parser.add_argument('--location', type=str, default='Cameroon Far North', help='Location for analysis')
    parser.add_argument('--forecast-hours', type=int, default=24, help='Forecast horizon in hours')
    parser.add_argument('--scenario', type=str, default='routine_check', 
                       choices=['routine_check', 'flash_flood_alert'], help='Emergency response scenario')
    parser.add_argument('--ml-task', type=str, default='train_model',
                       choices=['train_model', 'analyze_performance', 'optimize_features'], help='H2OGPTE ML task type')
    parser.add_argument('--list-agents', action='store_true', help='List available agents')
    parser.add_argument('--output-file', type=str, help='Save results to file')
    
    args = parser.parse_args()
    
    runner = FloodPredictionRunner()
    
    if args.list_agents:
        agents_info = runner.list_available_agents()
        print(json.dumps(agents_info, indent=2))
        return
    
    if not NAT_AVAILABLE:
        logger.error("NVIDIA NAT is not available. Please install it first.")
        return
    
    # Run specified agent or comprehensive analysis
    if args.agent == 'data_collector':
        result = await runner.run_data_collector(args.prompt)
    elif args.agent == 'risk_analyzer':
        result = await runner.run_risk_analyzer(args.location, args.prompt)
    elif args.agent == 'emergency_responder':
        result = await runner.run_emergency_responder(args.scenario, args.prompt)
    elif args.agent == 'predictor':
        result = await runner.run_predictor(args.forecast_hours, args.location, args.prompt)
    elif args.agent == 'h2ogpte_agent':
        user_query = args.prompt or f"Please help with {args.ml_task} for flood prediction"
        result = await runner.run_h2ogpte_agent(args.ml_task, user_query, args.prompt)
    else:  # all
        result = await runner.run_comprehensive_analysis()
    
    # Output results
    if args.output_file:
        with open(args.output_file, 'w') as f:
            json.dump(result, f, indent=2)
        logger.info(f"Results saved to {args.output_file}")
    else:
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
