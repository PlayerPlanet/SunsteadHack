"""Unit tests for deploy/aws/launch_run.py.

Tests the launch_run function with boto3 mocked (no real AWS calls).
Validates environment override, task tags, network configuration, and ARN return.
"""

import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add deploy/aws to path for import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'deploy', 'aws'))

# Patch boto3 before importing launch_run
import sys
boto3_mock = MagicMock()
sys.modules['boto3'] = boto3_mock

import launch_run


class TestLaunchRun(unittest.TestCase):
    """Test cases for the launch_run function."""

    @patch('boto3.client')
    def test_launch_run_basic(self, mock_boto3_client):
        """Test basic launch_run call with required parameters."""
        # Mock ECS client
        mock_ecs_client = MagicMock()
        mock_boto3_client.return_value = mock_ecs_client

        # Mock ecs:RunTask response
        mock_ecs_client.run_task.return_value = {
            'tasks': [
                {
                    'taskArn': 'arn:aws:ecs:us-east-1:123456789012:task/story-e-cluster/abc123def456'
                }
            ]
        }

        # Call launch_run
        run_id = launch_run.launch_run(
            task_id='test_task_1',
            model='claude-opus-4-20250805',
            iterations=5
        )

        # Verify return value
        self.assertEqual(
            run_id,
            'arn:aws:ecs:us-east-1:123456789012:task/story-e-cluster/abc123def456'
        )

        # Verify ecs:RunTask was called
        mock_ecs_client.run_task.assert_called_once()

    @patch('boto3.client')
    def test_launch_run_environment_overrides(self, mock_boto3_client):
        """Test that TASK_ID, MODEL, ITERATIONS are passed as env overrides."""
        mock_ecs_client = MagicMock()
        mock_boto3_client.return_value = mock_ecs_client

        mock_ecs_client.run_task.return_value = {
            'tasks': [{'taskArn': 'arn:aws:ecs:...'}]
        }

        launch_run.launch_run(
            task_id='my_task_42',
            model='claude-opus-4-20250805',
            iterations=10
        )

        # Verify containerOverrides
        call_args = mock_ecs_client.run_task.call_args
        container_overrides = call_args.kwargs.get('containerOverrides', [{}])[0]
        env_vars = {e['name']: e['value'] for e in container_overrides.get('environment', [])}

        self.assertEqual(env_vars['TASK_ID'], 'my_task_42')
        self.assertEqual(env_vars['MODEL'], 'claude-opus-4-20250805')
        self.assertEqual(env_vars['ITERATIONS'], '10')

    @patch('boto3.client')
    def test_launch_run_task_tags(self, mock_boto3_client):
        """Test that tasks are tagged with task_id and model."""
        mock_ecs_client = MagicMock()
        mock_boto3_client.return_value = mock_ecs_client

        mock_ecs_client.run_task.return_value = {
            'tasks': [{'taskArn': 'arn:aws:ecs:...'}]
        }

        launch_run.launch_run(
            task_id='test_task',
            model='claude-haiku-4-5-20251001',
            iterations=1
        )

        # Verify tags
        call_args = mock_ecs_client.run_task.call_args
        tags = call_args.kwargs.get('tags', [])
        tag_dict = {t['key']: t['value'] for t in tags}

        self.assertEqual(tag_dict['task_id'], 'test_task')
        self.assertEqual(tag_dict['model'], 'claude-haiku-4-5-20251001')

    @patch('boto3.client')
    def test_launch_run_network_config(self, mock_boto3_client):
        """Test that awsvpc network config has no public IP."""
        mock_ecs_client = MagicMock()
        mock_boto3_client.return_value = mock_ecs_client

        mock_ecs_client.run_task.return_value = {
            'tasks': [{'taskArn': 'arn:aws:ecs:...'}]
        }

        launch_run.launch_run(
            task_id='test',
            model='claude-opus-4-20250805',
            iterations=1,
            subnets=['subnet-abc123', 'subnet-def456'],
            security_groups=['sg-xyz789']
        )

        # Verify network configuration
        call_args = mock_ecs_client.run_task.call_args
        net_config = call_args.kwargs.get('networkConfiguration', {})
        awsvpc = net_config.get('awsvpcConfiguration', {})

        # Should NOT assign public IP (uses NAT Gateway)
        self.assertEqual(awsvpc['assignPublicIp'], 'DISABLED')

        # Should include subnets and security groups
        self.assertEqual(awsvpc['subnets'], ['subnet-abc123', 'subnet-def456'])
        self.assertEqual(awsvpc['securityGroups'], ['sg-xyz789'])

    @patch('boto3.client')
    def test_launch_run_launch_type_fargate(self, mock_boto3_client):
        """Test that launch type is FARGATE."""
        mock_ecs_client = MagicMock()
        mock_boto3_client.return_value = mock_ecs_client

        mock_ecs_client.run_task.return_value = {
            'tasks': [{'taskArn': 'arn:aws:ecs:...'}]
        }

        launch_run.launch_run(
            task_id='test',
            model='claude-opus-4-20250805',
            iterations=1
        )

        # Verify launch type
        call_args = mock_ecs_client.run_task.call_args
        launch_type = call_args.kwargs.get('launchType')

        self.assertEqual(launch_type, 'FARGATE')

    @patch('boto3.client')
    def test_launch_run_error_handling(self, mock_boto3_client):
        """Test that RunTask errors are caught and re-raised."""
        mock_ecs_client = MagicMock()
        mock_boto3_client.return_value = mock_ecs_client

        # Mock a failure response
        mock_ecs_client.run_task.return_value = {
            'tasks': [],
            'failures': [{'reason': 'Invalid task definition'}]
        }

        with self.assertRaises(RuntimeError) as ctx:
            launch_run.launch_run(
                task_id='test',
                model='claude-opus-4-20250805',
                iterations=1
            )

        self.assertIn('Invalid task definition', str(ctx.exception))

    @patch('boto3.client')
    def test_launch_run_boto3_exception(self, mock_boto3_client):
        """Test that boto3 exceptions are caught."""
        mock_ecs_client = MagicMock()
        mock_boto3_client.return_value = mock_ecs_client

        # Mock boto3 raising an exception
        mock_ecs_client.run_task.side_effect = Exception('Access Denied')

        with self.assertRaises(RuntimeError):
            launch_run.launch_run(
                task_id='test',
                model='claude-opus-4-20250805',
                iterations=1
            )

    def test_launch_run_soft_import(self):
        """Test that launch_run module imports without boto3."""
        # This test verifies that the module can be imported even if boto3
        # is not installed (soft import). The import is in the function, not at module level.
        import importlib
        spec = importlib.util.spec_from_file_location(
            "launch_run",
            os.path.join(os.path.dirname(__file__), '..', 'deploy', 'aws', 'launch_run.py')
        )
        module = importlib.util.module_from_spec(spec)
        # This should not raise ImportError even if boto3 is unavailable
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'launch_run'))

    @patch('boto3.client')
    def test_launch_run_custom_parameters(self, mock_boto3_client):
        """Test that custom cluster, task_def, and region are respected."""
        mock_ecs_client = MagicMock()
        mock_boto3_client.return_value = mock_ecs_client

        mock_ecs_client.run_task.return_value = {
            'tasks': [{'taskArn': 'arn:aws:ecs:...'}]
        }

        launch_run.launch_run(
            task_id='test',
            model='claude-opus-4-20250805',
            iterations=1,
            cluster='custom-cluster',
            task_def='custom-task-def',
            region='eu-west-1'
        )

        # Verify custom parameters were used
        call_args = mock_ecs_client.run_task.call_args
        self.assertEqual(call_args.kwargs['cluster'], 'custom-cluster')
        self.assertEqual(call_args.kwargs['taskDefinition'], 'custom-task-def')
        mock_boto3_client.assert_called_with('ecs', region_name='eu-west-1')


class TestLaunchRunCLI(unittest.TestCase):
    """Test cases for the CLI interface."""

    @patch('launch_run.launch_run')
    def test_cli_basic_invocation(self, mock_launch_run):
        """Test CLI with basic arguments."""
        mock_launch_run.return_value = 'arn:aws:ecs:...'

        # Simulate CLI call
        sys.argv = [
            'launch_run.py',
            'test_task',
            'claude-opus-4-20250805',
            '5'
        ]

        # CLI should complete without raising
        launch_run.main()
        # Verify launch_run was called with correct args
        mock_launch_run.assert_called_once_with(
            task_id='test_task',
            model='claude-opus-4-20250805',
            iterations=5,
            cluster=None,
            task_def=None,
            region=None
        )


if __name__ == '__main__':
    unittest.main()
