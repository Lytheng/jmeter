#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
import json
import base64
import os
import html
from datetime import datetime

now = datetime.now()  # current date and time
date_time = now.strftime("%d-%m-%Y-%H-%M-%S")
IS_DOCKER = os.environ.get('APP_ENV', False)

def parse_jtl_file(file_path):
    """Parse the JTL file and extract test cases and steps with proper hierarchical structure."""
    tree = ET.parse(file_path)
    root = tree.getroot()
    
    test_cases = []
    
    # Find all direct children of the root element in order they appear
    for element in root:
        # Only process sample or httpSample elements with an 'lb' attribute
        if element.tag in ['sample', 'httpSample'] and 'lb' in element.attrib:
            test_case = create_test_case(element)
            # Recursively process all children to maintain the hierarchy
            process_child_elements(element, test_case)
            
            # After processing all children, update the test case status based on assertions
            update_status_based_on_assertions(test_case)
            
            test_cases.append(test_case)
    
    return test_cases

def process_child_elements(parent_element, parent_data):
    """Recursively process all child elements and maintain hierarchy."""
    for child in parent_element:
        # Process only sample and httpSample elements that have a label attribute
        if child.tag in ['sample', 'httpSample'] and 'lb' in child.attrib:
            step_data = {
                'name': child.get('lb', 'Unnamed Step'),
                'status': child.get('s', 'false') == 'true',
                'time': float(child.get('t', '0')),
                'timestamp': child.get('ts', '0'),
                'response_code': child.get('rc', ''),
                'response_message': child.get('rm', ''),
                'element_type': child.tag,
                'url': '',
                'request_header': '',
                'response_header': '',
                'response_data': '',
                'request_data': '',
                'steps': [],  # For further nesting of steps
                'assertions': [],  # Add assertions array
                'failure_message': ''  # Add failure message field
            }
            
            # Extract failure message if present
            failure_msg = child.find('./failureMessage')
            if failure_msg is not None and failure_msg.text:
                step_data['failure_message'] = failure_msg.text
            
            # Look for queryString and add raw data directly for special handling
            query_string = child.find('./queryString')
            if query_string is not None and query_string.text:
                step_data['raw_query_string'] = query_string.text
                
            # Look for samplerData and add raw data directly for special handling
            sampler_data = child.find('./samplerData')
            if sampler_data is not None and sampler_data.text:
                step_data['raw_sampler_data'] = sampler_data.text
            
            # Extract request/response data
            extract_request_response_data(child, step_data)
            
            # Extract assertion results
            extract_assertion_results(child, step_data)
            
            # Recursively process this child's children to maintain the hierarchy
            process_child_elements(child, step_data)
            
            # Add this step to the parent's steps
            parent_data['steps'].append(step_data)

def extract_request_response_data(element, data_dict):
    """Extract request and response data from an element."""
    # Get URL
    url = element.find('./java.net.URL')
    if url is not None and url.text:
        data_dict['url'] = url.text
    
    # Initialize request_data if not present
    if 'request_data' not in data_dict:
        data_dict['request_data'] = ''
    
    # Get queryString and process exactly as shown in the XML
    query_string = element.find('./queryString')
    if query_string is not None and query_string.text:
        # Process raw text directly
        raw_text = query_string.text
        
        # Special handling for carriage returns in XML
        raw_text = raw_text.replace('\r', '\r')  # Fixed syntax error here
        
        # Unescape HTML entities like &quot;
        decoded_text = html.unescape(raw_text)
        
        # Clean up carriage returns for JSON
        cleaned_text = decoded_text.replace('\r\n', '').replace('\r', '').replace('\n', '')
        cleaned_text = cleaned_text.strip()
        
        try:
            # Try to parse as JSON
            json_data = json.loads(cleaned_text)
            formatted_json = json.dumps(json_data, indent=2, ensure_ascii=False)
            data_dict['request_data'] = formatted_json
        except json.JSONDecodeError:
            # If not valid JSON, use the raw text
            data_dict['request_data'] = cleaned_text
    
    # If still no request data, try samplerData
    if not data_dict['request_data']:
        sampler_data = element.find('./samplerData')
        if sampler_data is not None and sampler_data.text:
            raw_text = sampler_data.text
            
            # Special handling for carriage returns in XML
            raw_text = raw_text.replace('\r', '\r')
            
            # Unescape HTML entities like &quot;
            decoded_text = html.unescape(raw_text)
            
            # Clean up carriage returns for JSON
            cleaned_text = decoded_text.replace('\r\n', '').replace('\r', '').replace('\n', '')
            cleaned_text = cleaned_text.strip()
            
            try:
                # Try to parse as JSON
                json_data = json.loads(cleaned_text)
                formatted_json = json.dumps(json_data, indent=2, ensure_ascii=False)
                data_dict['request_data'] = formatted_json
            except json.JSONDecodeError:
                # If not valid JSON, use the raw text
                data_dict['request_data'] = cleaned_text
    
    # If still no request data, try alternate locations
    if not data_dict['request_data']:
        # Try to find request data in a requestBody element
        request_body = element.find('./requestBody')
        if request_body is not None and request_body.text:
            decoded_text = html.unescape(request_body.text)
            data_dict['request_data'] = decoded_text
    
    # Get request headers
    request_header = element.find('./requestHeader')
    if request_header is not None and request_header.text:
        data_dict['request_header'] = request_header.text
    
    # Get response headers
    response_header = element.find('./responseHeader')
    if response_header is not None and response_header.text:
        data_dict['response_header'] = response_header.text
    
    # Get response data
    response_data = element.find('./responseData')
    if response_data is not None and response_data.text:
        data_dict['response_data'] = response_data.text

def extract_assertion_results(element, data_dict):
    """Extract assertion results from an element."""
    assertion_results = element.findall('./assertionResult')
    data_dict['assertions'] = []
    
    for assertion in assertion_results:
        assertion_name = assertion.find('./n')
        assertion_failure = assertion.find('./failure')
        assertion_error = assertion.find('./e')
        assertion_message = assertion.find('./m')
        failure_message = assertion.find('./failureMessage')
        
        assertion_data = {
            'name': assertion_name.text if assertion_name is not None else 'Unnamed Assertion',
            'failure': assertion_failure.text == 'true' if assertion_failure is not None else False,
            'error': assertion_error.text == 'true' if assertion_error is not None else False,
            'message': assertion_message.text if assertion_message is not None else '',
            'failure_message': failure_message.text if failure_message is not None and failure_message.text else ''
        }
        
        data_dict['assertions'].append(assertion_data)
        
        # If this assertion has a failure message and the parent doesn't have one yet, add it
        if assertion_data['failure_message'] and not data_dict.get('failure_message'):
            data_dict['failure_message'] = assertion_data['failure_message']

def create_test_case(sample):
    """Create a test case dictionary from a sample element."""
    test_case = {
        'name': sample.get('lb', 'Unnamed Test'),
        'status': sample.get('s', 'false') == 'true',
        'time': float(sample.get('t', '0')),
        'timestamp': sample.get('ts', '0'),
        'response_code': sample.get('rc', ''),
        'response_message': sample.get('rm', ''),
        'thread_name': sample.get('tn', ''),
        'steps': [],  # For child steps
        'request_header': '',
        'response_header': '',
        'response_data': '',
        'request_data': '',  # Ensure request_data is initialized
        'url': '',
        'assertions': [],  # Add assertions array
        'failure_message': ''  # Add failure message field
    }
    
    # Extract failure message if present
    failure_msg = sample.find('./failureMessage')
    if failure_msg is not None and failure_msg.text:
        test_case['failure_message'] = failure_msg.text
    
    # Look for queryString and add raw data directly for special handling
    query_string = sample.find('./queryString')
    if query_string is not None and query_string.text:
        test_case['raw_query_string'] = query_string.text
    
    # Look for samplerData and add raw data directly for special handling
    sampler_data = sample.find('./samplerData')
    if sampler_data is not None and sampler_data.text:
        test_case['raw_sampler_data'] = sampler_data.text
    
    # Extract request/response data
    extract_request_response_data(sample, test_case)
    
    # Extract assertion results
    extract_assertion_results(sample, test_case)
    
    return test_case

def update_status_based_on_assertions(item):
    """Update the status of an item (test case or step) based on its assertions and child steps."""
    # Check if any assertions in this item failed
    has_failed_assertions = any(assertion.get('failure', False) or assertion.get('error', False) 
                                for assertion in item.get('assertions', []))
    
    # Check if any child steps have failed assertions
    has_failed_child = False
    for step in item.get('steps', []):
        # First update the child's status recursively
        update_status_based_on_assertions(step)
        # Then check if the child is now failed
        if not step['status']:
            has_failed_child = True
    
    # Update item status - fail if any assertions failed or any child steps failed
    if has_failed_assertions or has_failed_child:
        item['status'] = False

def calculate_statistics(test_cases):
    """Calculate statistics for the test cases."""
    total_tests = len(test_cases)
    passed_tests = sum(1 for tc in test_cases if tc['status'])
    failed_tests = total_tests - passed_tests
    
    # Calculate total test duration (from earliest timestamp to latest timestamp + duration)
    if total_tests > 0:
        # Convert timestamps to integers for comparison
        timestamps = [int(tc['timestamp']) for tc in test_cases if tc['timestamp']]
        if timestamps:
            min_timestamp = min(timestamps)
            # Find the end time of the last test (timestamp + duration)
            max_end_time = max([int(tc['timestamp']) + tc['time'] for tc in test_cases if tc['timestamp']])
            total_duration = max_end_time - min_timestamp
        else:
            # If no timestamps, sum up all test durations
            total_duration = sum(tc['time'] for tc in test_cases)
    else:
        total_duration = 0
    
    # Count assertions
    total_assertions = 0
    passed_assertions = 0
    failed_assertions = 0
    
    # Function to recursively count assertions in test cases and their steps
    def count_assertions(item):
        nonlocal total_assertions, passed_assertions, failed_assertions
        
        # Count assertions in the current item
        for assertion in item.get('assertions', []):
            total_assertions += 1
            if not assertion.get('failure', False) and not assertion.get('error', False):
                # Only count as passed if the parent sample also passed
                if item.get('status', True):
                    passed_assertions += 1
                else:
                    # If sample failed but assertion shows passed, count as failed
                    failed_assertions += 1
            else:
                failed_assertions += 1
        
        # Recursively count assertions in steps
        for step in item.get('steps', []):
            count_assertions(step)
    
    # Count assertions in all test cases
    for test_case in test_cases:
        count_assertions(test_case)
    
    # Collect performance data by endpoint
    endpoint_performance = {}
    
    # Function to extract endpoint from URL
    def extract_endpoint(url):
        if not url:
            return "Unknown Endpoint"
        
        # Parse the URL
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            # Get the path part of the URL
            path = parsed_url.path
            
            # Remove trailing slash if present
            if path.endswith('/'):
                path = path[:-1]
                
            # If path is empty, use the hostname
            if not path:
                return parsed_url.netloc
                
            # Return the path as the endpoint
            return path
        except:
            # If parsing fails, return the original URL
            return url
    
    # Function to recursively collect performance data from test cases and their steps
    def collect_endpoint_performance(item):
        # Add the current item to performance data if it has a URL
        if 'url' in item and item['url']:
            endpoint = extract_endpoint(item['url'])
            
            # Initialize endpoint data if not already present
            if endpoint not in endpoint_performance:
                endpoint_performance[endpoint] = {
                    'total_time': 0,
                    'count': 0,
                    'success_count': 0,
                    'fail_count': 0,
                    'min_time': float('inf'),
                    'max_time': 0
                }
            
            # Update endpoint statistics
            endpoint_data = endpoint_performance[endpoint]
            endpoint_data['total_time'] += item['time']
            endpoint_data['count'] += 1
            if item['status']:
                endpoint_data['success_count'] += 1
            else:
                endpoint_data['fail_count'] += 1
            
            # Update min and max times
            endpoint_data['min_time'] = min(endpoint_data['min_time'], item['time'])
            endpoint_data['max_time'] = max(endpoint_data['max_time'], item['time'])
        
        # Recursively collect performance data from steps
        for step in item.get('steps', []):
            collect_endpoint_performance(step)
    
    # Collect performance data from all test cases
    for test_case in test_cases:
        collect_endpoint_performance(test_case)
    
    # Calculate average response time for each endpoint
    endpoint_performance_list = []
    for endpoint, data in endpoint_performance.items():
        # Calculate average time
        avg_time = data['total_time'] / data['count'] if data['count'] > 0 else 0
        
        # Calculate success rate
        success_rate = (data['success_count'] / data['count']) * 100 if data['count'] > 0 else 0
        
        endpoint_performance_list.append({
            'name': endpoint,
            'avg_time': avg_time,
            'min_time': data['min_time'] if data['min_time'] != float('inf') else 0,
            'max_time': data['max_time'],
            'count': data['count'],
            'success_count': data['success_count'],
            'fail_count': data['fail_count'],
            'success_rate': success_rate
        })
    
    # Sort by average response time (descending)
    endpoint_performance_list.sort(key=lambda x: x['avg_time'], reverse=True)
    
    # Take top 20 for the graph to avoid overcrowding
    top_endpoints = endpoint_performance_list[:20]
    
    return {
        'total': total_tests,
        'passed': passed_tests,
        'failed': failed_tests,
        'pass_percentage': (passed_tests / total_tests) * 100 if total_tests > 0 else 0,
        'total_duration': total_duration,
        'total_assertions': total_assertions,
        'passed_assertions': passed_assertions,
        'failed_assertions': failed_assertions,
        'assertion_pass_percentage': (passed_assertions / total_assertions) * 100 if total_assertions > 0 else 0,
        'endpoint_performance': top_endpoints
    }

def format_time(milliseconds):
    """Format time in milliseconds to a readable format."""
    if milliseconds < 1000:
        return f"{milliseconds:.2f} ms"
    else:
        seconds = milliseconds / 1000
        if seconds < 60:
            return f"{seconds:.2f} s"
        else:
            minutes = seconds / 60
            return f"{minutes:.2f} min"

def format_timestamp(milliseconds):
    """Convert Unix timestamp in milliseconds to a readable datetime string."""
    try:
        # Convert milliseconds to seconds and then to datetime
        seconds = int(milliseconds) / 1000
        dt = datetime.fromtimestamp(seconds)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return "Invalid Timestamp"

def get_status_badge(status):
    """Get HTML status badge based on status."""
    if status:
        return '<span class="badge bg-success">PASSED</span>'
    else:
        return '<span class="badge bg-danger">FAILED</span>'

def escape_html(text):
    """Escape HTML special characters."""
    if text is None:
        return ""
    return (text.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace("\"", "&quot;")
               .replace("'", "&#x27;"))

def render_json(text):
    """Format JSON text for display."""
    if not text:
        return ""
    
    # Remove any leading/trailing whitespace
    text = text.strip()
    
    try:
        # Try to parse as JSON
        # First try direct parsing
        try:
            data = json.loads(text)
            return json.dumps(data, indent=2, ensure_ascii=False)
        except:
            # If that fails, try handling common JMeter encoding patterns
            # Sometimes JMeter uses \r\n and other escape sequences that need to be processed
            processed_text = text.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\"', '"')
            # Try to remove any outer quotes if they exist
            if (processed_text.startswith('"') and processed_text.endswith('"')) or \
               (processed_text.startswith("'") and processed_text.endswith("'")):
                processed_text = processed_text[1:-1]
            
            try:
                data = json.loads(processed_text)
                return json.dumps(data, indent=2, ensure_ascii=False)
            except:
                # If still not valid JSON, return as is with newlines formatted
                if '\\r\\n' in text or '\\n' in text:
                    return text.replace('\\r\\n', '\n').replace('\\n', '\n')
                return text
    except:
        # If not valid JSON, return as is
        return text

def code_block_with_copy(content, code_id, language="json"):
    """Create a code block with a copy button."""
    return f"""<div class="code-container position-relative">
        <button class="btn btn-sm btn-outline-secondary copy-btn position-absolute top-0 end-0 m-2" 
                id="btn-{code_id}" onclick="copyToClipboard('{code_id}')">
            <i class="bi bi-clipboard"></i> Copy
        </button>
        <pre><code id="{code_id}" class="{language}">{escape_html(content)}</code></pre>
    </div>"""

def url_with_copy(url, url_id):
    """Create a URL display with a copy button."""
    if not url:
        return '<span class="text-muted">No URL</span>'
    
    return f"""<div class="url-container d-flex align-items-center">
        <span id="{url_id}" class="me-2">{escape_html(url)}</span>
        <button class="btn btn-sm btn-outline-secondary copy-btn-sm" 
                id="btn-{url_id}" onclick="copyToClipboard('{url_id}')">
            <i class="bi bi-clipboard"></i>
        </button>
    </div>"""

def generate_html_report(test_cases, stats, output_file):
    """Generate HTML report from test cases and statistics."""
    now = datetime.now()
    date_time = now.strftime("%Y-%m-%d %H:%M:%S")
    next_id = 1
    
    # Prepare performance data for JavaScript
    performance_labels = json.dumps([escape_html(item["name"]) for item in stats['endpoint_performance']], ensure_ascii=False)
    performance_data = json.dumps([item["avg_time"] for item in stats['endpoint_performance']])
    performance_min_times = json.dumps([item["min_time"] for item in stats['endpoint_performance']])
    performance_max_times = json.dumps([item["max_time"] for item in stats['endpoint_performance']])
    performance_counts = json.dumps([item["count"] for item in stats['endpoint_performance']])
    performance_success_rates = json.dumps([item["success_rate"] for item in stats['endpoint_performance']])
    performance_bg_colors = json.dumps(["rgba(40, 167, 69, 0.7)" if item["success_rate"] >= 90 else "rgba(220, 53, 69, 0.7)" for item in stats['endpoint_performance']])
    performance_border_colors = json.dumps(["rgb(40, 167, 69)" if item["success_rate"] >= 90 else "rgb(220, 53, 69)" for item in stats['endpoint_performance']])
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Automation Test Report</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.5.0/styles/default.min.css">
    <style>
        body {{ padding-top: 20px; padding-bottom: 50px; }}
        .dashboard-card {{ transition: all 0.3s; }}
        .dashboard-card:hover {{ transform: translateY(-5px); box-shadow: 0 10px 20px rgba(0,0,0,0.1); }}
        .test-case {{ 
            margin-bottom: 20px; 
            border: 1px solid #ddd; 
            border-radius: 5px; 
            overflow: hidden; 
            width: 100%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            transition: all 0.3s ease;
        }}
        .test-case:hover {{ 
            box-shadow: 0 4px 8px rgba(0,0,0,0.1); 
        }}
        .test-case-header {{ 
            padding: 10px 15px; 
            background-color: #f8f9fa; 
            cursor: pointer; 
            border-bottom: 1px solid #eee;
        }}
        .test-case-header:hover {{ background-color: #e9ecef; }}
        .test-case-body {{ padding: 15px; display: none; }}
        .test-step {{ 
            margin-bottom: 15px; 
            border: 1px solid #eee; 
            border-radius: 5px; 
            width: 100%;
        }}
        .test-step-header {{ padding: 8px 15px; background-color: #f1f3f5; cursor: pointer; }}
        .test-step-header:hover {{ background-color: #e9ecef; }}
        .test-step-body {{ padding: 15px; display: none; }}
        .data-container {{ margin-top: 10px; }}
        .nav-tabs {{ margin-bottom: 15px; }}
        pre {{ max-height: 500px; overflow: auto; }}
        .progress {{ height: 25px; }}
        .progress-bar {{ line-height: 25px; }}
        .code-container {{ position: relative; }}
        .copy-btn {{ 
            position: absolute; 
            top: 5px; 
            right: 5px; 
            z-index: 10;
            opacity: 0.7;
        }}
        .copy-btn:hover {{ 
            opacity: 1; 
        }}
        .copy-success {{
            background-color: #28a745;
            color: white;
        }}
        .copy-btn-sm {{
            padding: 0.25rem 0.5rem;
            font-size: 0.75rem;
            opacity: 0.7;
        }}
        .copy-btn-sm:hover {{
            opacity: 1;
        }}
        .url-container {{
            margin-bottom: 0.5rem;
        }}
        /* New enhanced styles */
        .test-case-header {{
            background: linear-gradient(to right, #f8f9fa, #e9ecef);
            border-left: 5px solid #6c757d;
            transition: all 0.2s ease;
        }}
        .test-case-header:hover {{
            background: linear-gradient(to right, #e9ecef, #dee2e6);
        }}
        .test-case.passed .test-case-header {{
            border-left-color: #28a745;
        }}
        .test-case.failed .test-case-header {{
            border-left-color: #dc3545;
        }}
        .test-step-header {{
            background: linear-gradient(to right, #f1f3f5, #e9ecef);
            border-left: 4px solid #adb5bd;
            transition: all 0.2s ease;
        }}
        .test-step.passed .test-step-header {{
            border-left-color: #28a745;
        }}
        .test-step.failed .test-step-header {{
            border-left-color: #dc3545;
        }}
        .badge {{
            font-size: 0.85rem;
            padding: 0.4em 0.6em;
        }}
        .test-controls {{
            margin-bottom: 20px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .search-box {{
            position: relative;
            margin-bottom: 15px;
        }}
        .search-box input {{
            padding-left: 35px;
            border-radius: 20px;
        }}
        .search-icon {{
            position: absolute;
            left: 10px;
            top: 10px;
            color: #6c757d;
        }}
        .filter-btn {{
            margin-right: 5px;
            border-radius: 20px;
        }}
        .toggle-all-btn {{
            margin-left: 10px;
            border-radius: 20px;
        }}
        .test-case-time, .test-step-time {{
            color: #6c757d;
            font-size: 0.85rem;
        }}
        .tree-indent {{
            margin-left: 1.5rem;
        }}
        .overview-panel {{
            position: sticky;
            top: 20px;
            max-height: calc(100vh - 40px);
            overflow-y: auto;
        }}
        .card-header {{
            font-weight: 500;
        }}
        /* Extra UI improvements for dashboard */
        .dashboard-card {{
            border-radius: 10px;
            border: none;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .container {{
            max-width: 1300px;
        }}
        .logo-container {{
            text-align: right;
            margin-bottom: 30px;
            padding-top: 20px;
            padding-right: 15px;
            position: relative;
        }}
        .logo-img {{
            max-height: 60px;
            display: inline-block;
        }}
        h1.mb-4.text-center {{
            font-weight: 700;
            margin-top: 25px;
            margin-bottom: 20px !important;
            clear: both;
        }}
        @media (max-width: 768px) {{
            .test-controls .row {{
                flex-direction: column;
            }}
            .test-controls .col-md-6 {{
                width: 100%;
                margin-bottom: 10px;
            }}
            .d-flex.justify-content-end {{
                justify-content: flex-start !important;
            }}
        }}
        .nested-steps {{
            padding-left: 20px;
            border-left: 2px solid #e9ecef;
        }}
        .tree-indent-level-1 {{ margin-left: 20px; }}
        .tree-indent-level-2 {{ margin-left: 40px; }}
        .tree-indent-level-3 {{ margin-left: 60px; }}
        .tree-indent-level-4 {{ margin-left: 80px; }}
        .tree-indent-level-5 {{ margin-left: 100px; }}
        .assertion-badge {{
            display: inline-block;
            margin-right: 5px;
            margin-bottom: 5px;
        }}
        .assertion-message {{
            font-style: italic;
            color: #6c757d;
            margin-top: 5px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-container">
            <img src="https://www.ababank.com/typo3conf/ext/boxmodel/Resources/Private/Templates/ABA/images/aba-web-top-logo.png" alt="ABA Bank Logo" class="logo-img">
        </div>
        <h1 class="mb-4 text-center">Automation Test Report</h1>
        <p class="text-center text-muted">Generated on {date_time}</p>
        
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="card dashboard-card bg-primary text-white">
                    <div class="card-body text-center">
                        <h2>{stats['total']}</h2>
                        <p class="mb-0">Total Tests</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card dashboard-card bg-success text-white">
                    <div class="card-body text-center">
                        <h2>{stats['passed']}</h2>
                        <p class="mb-0">Passed Tests</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card dashboard-card bg-danger text-white">
                    <div class="card-body text-center">
                        <h2>{stats['failed']}</h2>
                        <p class="mb-0">Failed Tests</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card dashboard-card bg-info text-white">
                    <div class="card-body text-center">
                        <h2>{stats['pass_percentage']:.2f}%</h2>
                        <p class="mb-0">Pass Rate</p>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row mb-4">
            <div class="col-md-4">
                <div class="card dashboard-card">
                    <div class="card-header bg-secondary text-white">
                        <i class="bi bi-clock me-2"></i>Total Test Duration
                    </div>
                    <div class="card-body text-center">
                        <h3>{format_time(stats['total_duration'])}</h3>
                    </div>
                </div>
            </div>
            <div class="col-md-8">
                <div class="card dashboard-card">
                    <div class="card-header bg-secondary text-white">
                        <i class="bi bi-check-circle me-2"></i>Assertions Summary
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-3 text-center">
                                <h4>{stats['total_assertions']}</h4>
                                <p class="mb-0">Total</p>
                            </div>
                            <div class="col-md-3 text-center">
                                <h4 class="text-success">{stats['passed_assertions']}</h4>
                                <p class="mb-0">Passed</p>
                            </div>
                            <div class="col-md-3 text-center">
                                <h4 class="text-danger">{stats['failed_assertions']}</h4>
                                <p class="mb-0">Failed</p>
                            </div>
                            <div class="col-md-3 text-center">
                                <h4>{stats['assertion_pass_percentage']:.2f}%</h4>
                                <p class="mb-0">Success Rate</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="progress mb-4">
            <div class="progress-bar bg-success" role="progressbar" style="width: {stats['pass_percentage']}%"
                 aria-valuenow="{stats['pass_percentage']}" aria-valuemin="0" aria-valuemax="100">
                {stats['pass_percentage']:.2f}%
            </div>
            <div class="progress-bar bg-danger" role="progressbar" style="width: {100 - stats['pass_percentage']}%"
                 aria-valuenow="{100 - stats['pass_percentage']}" aria-valuemin="0" aria-valuemax="100">
                {100 - stats['pass_percentage']:.2f}%
            </div>
        </div>

        <!-- API Performance Graph -->
        <div class="card mb-4">
            <div class="card-header bg-secondary text-white">
                <i class="bi bi-graph-up me-2"></i>API Endpoint Performance (Top 20 by Avg Response Time)
            </div>
            <div class="card-body">
                <canvas id="performanceChart" height="300"></canvas>
            </div>
        </div>

        <div class="row">
            <div class="col-md-12">
                <!-- Test Controls -->
                <div class="test-controls">
                    <div class="row">
                        <div class="col-md-6">
                            <div class="search-box">
                                <i class="bi bi-search search-icon"></i>
                                <input type="text" class="form-control" id="searchInput" placeholder="Search test cases..." onkeyup="filterTestCases()">
                            </div>
                        </div>
                        <div class="col-md-6 d-flex justify-content-end">
                            <div class="btn-group" role="group">
                                <button type="button" class="btn btn-outline-secondary filter-btn active" onclick="filterByStatus('all')">All</button>
                                <button type="button" class="btn btn-outline-success filter-btn" onclick="filterByStatus('passed')">Passed</button>
                                <button type="button" class="btn btn-outline-danger filter-btn" onclick="filterByStatus('failed')">Failed</button>
                            </div>
                            <button type="button" class="btn btn-outline-primary toggle-all-btn" onclick="toggleAllTestCases()">Expand All</button>
                        </div>
                    </div>
                </div>

                <h2 class="mb-3">Test Cases <small class="text-muted">({stats['total']})</small></h2>
"""
    
    # Add this recursive function for rendering nested steps at any depth
    def render_nested_steps(steps, parent_id, depth=0):
        nonlocal next_id  # Make next_id accessible in this function
        html_content = ""
        indent_class = f"tree-indent-level-{depth}" if depth > 0 else ""
        
        for j, step in enumerate(steps):
            step_id = f"{parent_id}-{j}"
            step_status_badge = get_status_badge(step['status'])
            step_status_class = "passed" if step['status'] else "failed"
            
            html_content += f"""
                <div class="test-step {step_status_class} {indent_class}" data-status="{step_status_class}">
                    <div class="test-step-header d-flex justify-content-between align-items-center" onclick="toggleTestStep('{step_id}')">
                        <div>
                            <h6 class="mb-0"><i class="bi bi-file-earmark me-2"></i>{escape_html(step['name'])}</h6>
                            <small class="test-step-time">
                                <i class="bi bi-clock me-1"></i>Time: {format_time(step['time'])} |
                                <i class="bi bi-calendar me-1"></i>Timestamp: {format_timestamp(step['timestamp'])} |
                                <i class="bi bi-arrow-return-right me-1"></i>Response: {step['response_code']}
                            </small>
                        </div>
                        <div class="d-flex align-items-center">
                            {step_status_badge}
                            <span class="ms-2 toggle-step-icon-{step_id}"><i class="bi bi-chevron-down"></i></span>
                        </div>
                    </div>
                    <div class="test-step-body" id="test-step-{step_id}">
                        <div class="mb-3">
                            <strong><i class="bi bi-link-45deg me-1"></i>URL:</strong> {url_with_copy(step['url'], f"url-{next_id}")}
                        </div>
                        <div class="mb-3">
                            <strong><i class="bi bi-chat-dots me-1"></i>Response Message:</strong> {escape_html(step['response_message'])}
                        </div>"""
            
            # Add failure message section if it's not empty
            if step['failure_message']:
                html_content += f"""
                        <div class="mb-3">
                            <strong><i class="bi bi-exclamation-triangle-fill me-1 text-danger"></i>Failure Message:</strong>
                            <div class="mt-2 p-2 bg-light border rounded">
                                {escape_html(step['failure_message'])}
                            </div>
                        </div>"""
            
            # Add assertions section if there are any
            if step['assertions']:
                html_content += f"""
                        <div class="mb-3">
                            <strong><i class="bi bi-check-circle me-1"></i>Assertions:</strong>
                            <div class="mt-2">"""
                
                for assertion in step['assertions']:
                    assertion_status = "success" if not assertion['failure'] and not assertion['error'] else "danger"
                    assertion_icon = "check-circle-fill" if assertion_status == "success" else "x-circle-fill"
                    
                    html_content += f"""
                                <div class="assertion-badge badge bg-{assertion_status}">
                                    <i class="bi bi-{assertion_icon} me-1"></i>{escape_html(assertion['name'])}
                                </div>"""
                    
                    if assertion['message']:
                        html_content += f"""
                                <div class="assertion-message">{escape_html(assertion['message'])}</div>"""
                    
                    if assertion['failure_message']:
                        html_content += f"""
                                <div class="assertion-message text-danger">
                                    <i class="bi bi-exclamation-triangle-fill me-1"></i>
                                    {escape_html(assertion['failure_message'])}
                                </div>"""
                
                html_content += """
                            </div>
                        </div>"""
            
            html_content += f"""
                        <ul class="nav nav-tabs" role="tablist">
                            <li class="nav-item" role="presentation">
                                <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#step-request-{step_id}" type="button">
                                    <i class="bi bi-arrow-up-right me-1"></i>Request
                                </button>
                            </li>
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#step-response-{step_id}" type="button">
                                    <i class="bi bi-arrow-down-left me-1"></i>Response
                                </button>
                            </li>"""

            if step['steps']:
                html_content += f"""
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#step-substeps-{step_id}" type="button">
                                    <i class="bi bi-diagram-2 me-1"></i>Sub-Steps ({len(step['steps'])})
                                </button>
                            </li>"""

            html_content += f"""
                        </ul>
                        
                        <div class="tab-content">
                            <div class="tab-pane fade show active" id="step-request-{step_id}">
                                <div class="data-container">
                                    <h6><i class="bi bi-file-earmark-text me-1"></i>Request Data</h6>"""
            
            if 'raw_query_string' in step and step['raw_query_string'] and not step['request_data']:
                try:
                    raw_text = step['raw_query_string'].replace('\r', '\r')
                    decoded_text = html.unescape(raw_text)
                    cleaned_text = decoded_text.replace('\r\n', '').replace('\r', '').replace('\n', '')
                    cleaned_text = cleaned_text.strip()
                    json_data = json.loads(cleaned_text)
                    formatted_json = json.dumps(json_data, indent=2)
                    html_content += f"{code_block_with_copy(formatted_json, f'req-data-{next_id}')}"
                except:
                    html_content += f"{code_block_with_copy(step['raw_query_string'], f'req-data-{next_id}')}"
            elif 'raw_sampler_data' in step and step['raw_sampler_data'] and not step['request_data']:
                try:
                    raw_text = step['raw_sampler_data'].replace('\r', '\r')
                    decoded_text = html.unescape(raw_text)
                    cleaned_text = decoded_text.replace('\r\n', '').replace('\r', '').replace('\n', '')
                    cleaned_text = cleaned_text.strip()
                    json_data = json.loads(cleaned_text)
                    formatted_json = json.dumps(json_data, indent=2)
                    html_content += f"{code_block_with_copy(formatted_json, f'req-data-{next_id}')}"
                except:
                    html_content += f"{code_block_with_copy(step['raw_sampler_data'], f'req-data-{next_id}')}"
            else:
                html_content += f"{code_block_with_copy(render_json(step['request_data']), f'req-data-{next_id}')}"
            
            html_content += f"""
                                </div>
                                <div class="data-container">
                                    <h6><i class="bi bi-card-heading me-1"></i>Request Headers</h6>
                                    {code_block_with_copy(step['request_header'], f"req-header-{next_id}", "plaintext")}
                                </div>
                            </div>
                            <div class="tab-pane fade" id="step-response-{step_id}">
                                <div class="data-container">
                                    <h6><i class="bi bi-file-earmark-text me-1"></i>Response Data</h6>
                                    {code_block_with_copy(render_json(step['response_data']), f"resp-data-{next_id}")}
                                </div>
                                <div class="data-container">
                                    <h6><i class="bi bi-card-heading me-1"></i>Response Headers</h6>
                                    {code_block_with_copy(step['response_header'], f"resp-header-{next_id}", "plaintext")}
                                </div>
                            </div>"""

            if step['steps']:
                html_content += f"""
                            <div class="tab-pane fade" id="step-substeps-{step_id}">
                                <div class="mt-3 nested-steps">
                                    {render_nested_steps(step['steps'], step_id, depth+1)}
                                </div>
                            </div>"""
            
            html_content += f"""
                        </div>
                    </div>
                </div>
            """
            next_id += 4  # Increment for URL and request/response copy elements
        
        return html_content

    # Generate HTML for each test case
    for i, test_case in enumerate(test_cases):
        status_badge = get_status_badge(test_case['status'])
        status_class = "passed" if test_case['status'] else "failed"
        
        html += f"""
        <div class="test-case {status_class}" data-status="{status_class}">
            <div class="test-case-header d-flex justify-content-between align-items-center" onclick="toggleTestCase({i})">
                <div>
                    <h5 class="mb-0"><i class="bi bi-folder me-2"></i>{escape_html(test_case['name'])}</h5>
                    <small class="test-case-time">
                        <i class="bi bi-clock me-1"></i>Time: {format_time(test_case['time'])} |
                        <i class="bi bi-arrow-return-right me-1"></i>Response: {test_case['response_code']}
                    </small>
                </div>
                <div class="d-flex align-items-center">
                    {status_badge}
                    <span class="ms-2 toggle-icon-{i}"><i class="bi bi-chevron-down"></i></span>
                </div>
            </div>
            <div class="test-case-body" id="test-case-{i}">
                <div class="mb-3">
                    <strong><i class="bi bi-people me-1"></i>Thread:</strong> {escape_html(test_case['thread_name'])}
                </div>
                <div class="mb-3">
                    <strong><i class="bi bi-link-45deg me-1"></i>URL:</strong> {url_with_copy(test_case['url'], f"testcase-url-{next_id}")}
                </div>
                <div class="mb-3">
                    <strong><i class="bi bi-chat-dots me-1"></i>Response Message:</strong> {escape_html(test_case['response_message'])}
                </div>"""
        
        # Add failure message section if it's not empty
        if test_case['failure_message']:
            html += f"""
                <div class="mb-3">
                    <strong><i class="bi bi-exclamation-triangle-fill me-1 text-danger"></i>Failure Message:</strong>
                    <div class="mt-2 p-2 bg-light border rounded">
                        {escape_html(test_case['failure_message'])}
                    </div>
                </div>"""
        
        # Add assertions section if there are any
        if test_case['assertions']:
            html += f"""
                <div class="mb-3">
                    <strong><i class="bi bi-check-circle me-1"></i>Assertions:</strong>
                    <div class="mt-2">"""
            
            for assertion in test_case['assertions']:
                assertion_status = "success" if not assertion['failure'] and not assertion['error'] else "danger"
                assertion_icon = "check-circle-fill" if assertion_status == "success" else "x-circle-fill"
                
                html += f"""
                        <div class="assertion-badge badge bg-{assertion_status}">
                            <i class="bi bi-{assertion_icon} me-1"></i>{escape_html(assertion['name'])}
                        </div>"""
                
                if assertion['message']:
                    html += f"""
                        <div class="assertion-message">{escape_html(assertion['message'])}</div>"""
                
                if assertion['failure_message']:
                    html += f"""
                        <div class="assertion-message text-danger">
                            <i class="bi bi-exclamation-triangle-fill me-1"></i>
                            {escape_html(assertion['failure_message'])}
                        </div>"""
            
            html += """
                    </div>
                </div>"""
        
        html += f"""
                <ul class="nav nav-tabs" role="tablist">
                    <li class="nav-item" role="presentation">
                        <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#steps-{i}" type="button">
                            <i class="bi bi-list-check me-1"></i>Steps ({len(test_case['steps'])})
                        </button>
                    </li>
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" data-bs-toggle="tab" data-bs-target="#request-{i}" type="button">
                            <i class="bi bi-arrow-up-right me-1"></i>Request
                        </button>
                    </li>
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" data-bs-toggle="tab" data-bs-target="#response-{i}" type="button">
                            <i class="bi bi-arrow-down-left me-1"></i>Response
                        </button>
                    </li>
                </ul>"""
        
        html += f"""
                <div class="tab-content">
                    <div class="tab-pane fade show active" id="steps-{i}">
                        <div class="mt-3">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <h5><i class="bi bi-diagram-3 me-2"></i>Test Steps</h5>
                                <button class="btn btn-sm btn-outline-secondary" onclick="toggleAllSteps({i})">
                                    <i class="bi bi-arrows-expand me-1"></i>Toggle All
                                </button>
                            </div>
                            {render_nested_steps(test_case['steps'], i)}
                        </div>
                    </div>
                    <div class="tab-pane fade" id="request-{i}">
                        <div class="data-container">
                            <h6><i class="bi bi-file-earmark-text me-1"></i>Request Data</h6>"""
        
        if 'raw_query_string' in test_case and test_case['raw_query_string'] and not test_case['request_data']:
            try:
                raw_text = test_case['raw_query_string'].replace('\r', '\r')
                decoded_text = html.unescape(raw_text)
                cleaned_text = decoded_text.replace('\r\n', '').replace('\r', '').replace('\n', '')
                cleaned_text = cleaned_text.strip()
                json_data = json.loads(cleaned_text)
                formatted_json = json.dumps(json_data, indent=2)
                html += f"{code_block_with_copy(formatted_json, f'test-req-data-{next_id}')}"
            except:
                html += f"{code_block_with_copy(test_case['raw_query_string'], f'test-req-data-{next_id}')}"
        elif 'raw_sampler_data' in test_case and test_case['raw_sampler_data'] and not test_case['request_data']:
            try:
                raw_text = test_case['raw_sampler_data'].replace('\r', '\r')
                decoded_text = html.unescape(raw_text)
                cleaned_text = decoded_text.replace('\r\n', '').replace('\r', '').replace('\n', '')
                cleaned_text = cleaned_text.strip()
                json_data = json.loads(cleaned_text)
                formatted_json = json.dumps(json_data, indent=2)
                html += f"{code_block_with_copy(formatted_json, f'test-req-data-{next_id}')}"
            except:
                html += f"{code_block_with_copy(test_case['raw_sampler_data'], f'test-req-data-{next_id}')}"
        else:
            html += f"{code_block_with_copy(render_json(test_case['request_data']), f'test-req-data-{next_id}')}"
            
        html += f"""
                        </div>
                        <div class="data-container">
                            <h6><i class="bi bi-card-heading me-1"></i>Request Headers</h6>
                            {code_block_with_copy(test_case['request_header'], f"test-req-header-{next_id}", "plaintext")}
                        </div>
                    </div>
                    <div class="tab-pane fade" id="response-{i}">
                        <div class="data-container">
                            <h6><i class="bi bi-file-earmark-text me-1"></i>Response Data</h6>
                            {code_block_with_copy(render_json(test_case['response_data']), f"test-resp-data-{next_id}")}
                        </div>
                        <div class="data-container">
                            <h6><i class="bi bi-card-heading me-1"></i>Response Headers</h6>
                            {code_block_with_copy(test_case['response_header'], f"test-resp-header-{next_id}", "plaintext")}
                        </div>
                    </div>
                </div>
            </div>
        </div>
"""
        next_id += 4  # Increment for the URL copy element plus the 3 copy elements for request/response
    
    # Add JavaScript for copy functionality and close HTML
    html += """
            </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.5.0/highlight.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.5.0/languages/json.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                hljs.highlightAll();
                
                // Render performance chart
                const performanceChart = document.getElementById('performanceChart');
                if (performanceChart) {
                    const performanceData = {
                        labels: """
    
    # Add performance labels
    html += performance_labels
    
    html += """,
                        datasets: [{
                            label: 'Avg Response Time (ms)',
                            data: """
    
    # Add performance data
    html += performance_data
    
    html += """,
                            backgroundColor: """
    
    # Add background colors
    html += performance_bg_colors
    
    html += """,
                            borderColor: """
    
    # Add border colors
    html += performance_border_colors
    
    html += """,
                            borderWidth: 1
                        }]
                    };
                    
                    new Chart(performanceChart, {
                        type: 'bar',
                        data: performanceData,
                        options: {
                            indexAxis: 'y',
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    display: false
                                },
                                tooltip: {
                                    callbacks: {
                                        label: function(context) {
                                            const index = context.dataIndex;
                                            const minTime = """
    
    # Add min times
    html += performance_min_times
    
    html += """[index];
                                            const maxTime = """
    
    # Add max times
    html += performance_max_times
    
    html += """[index];
                                            const count = """
    
    # Add counts
    html += performance_counts
    
    html += """[index];
                                            const successRate = """
    
    # Add success rates
    html += performance_success_rates
    
    html += """[index];
                                            
                                            return [
                                                `Avg Response Time: ${format_time_js(context.raw)}`,
                                                `Min: ${format_time_js(minTime)} | Max: ${format_time_js(maxTime)}`,
                                                `Requests: ${count} | Success Rate: ${successRate.toFixed(2)}%`
                                            ];
                                        }
                                    }
                                }
                            },
                            scales: {
                                x: {
                                    title: {
                                        display: true,
                                        text: 'Response Time (ms)'
                                    }
                                },
                                y: {
                                    ticks: {
                                        callback: function(value, index) {
                                            const label = this.getLabelForValue(value);
                                            // Truncate long labels
                                            return label.length > 50 ? label.substring(0, 47) + '...' : label;
                                        }
                                    }
                                }
                            }
                        }
                    });
                }
            });
            
            function format_time_js(milliseconds) {
                if (milliseconds < 1000) {
                    return milliseconds.toFixed(2) + " ms";
                } else {
                    const seconds = milliseconds / 1000;
                    if (seconds < 60) {
                        return seconds.toFixed(2) + " s";
                    } else {
                        const minutes = seconds / 60;
                        return minutes.toFixed(2) + " min";
                    }
                }
            }
            
            function toggleTestCase(id) {
                const body = document.getElementById('test-case-' + id);
                const icon = document.querySelector('.toggle-icon-' + id + ' i');
                
                if (body.style.display === 'block') {
                    body.style.display = 'none';
                    icon.className = 'bi bi-chevron-down';
                } else {
                    body.style.display = 'block';
                    icon.className = 'bi bi-chevron-up';
                }
            }
            
            function toggleTestStep(id) {
                const body = document.getElementById('test-step-' + id);
                const icon = document.querySelector('.toggle-step-icon-' + id + ' i');
                
                if (body.style.display === 'block') {
                    body.style.display = 'none';
                    icon.className = 'bi bi-chevron-down';
                } else {
                    body.style.display = 'block';
                    icon.className = 'bi bi-chevron-up';
                }
            }
            
            function toggleAllTestCases() {
                const button = document.querySelector('.toggle-all-btn');
                const allTestCaseBodies = document.querySelectorAll('.test-case-body');
                const allIcons = document.querySelectorAll('.toggle-icon-\\d+ i');
                
                // Check if any test case is already expanded
                let anyExpanded = false;
                for (let body of allTestCaseBodies) {
                    if (body.style.display === 'block') {
                        anyExpanded = true;
                        break;
                    }
                }
                
                // Toggle state based on current state
                if (anyExpanded) {
                    // Collapse all
                    for (let body of allTestCaseBodies) {
                        body.style.display = 'none';
                    }
                    for (let icon of allIcons) {
                        icon.className = 'bi bi-chevron-down';
                    }
                    button.innerHTML = '<i class="bi bi-arrows-expand me-1"></i>Expand All';
                } else {
                    // Expand all
                    for (let body of allTestCaseBodies) {
                        body.style.display = 'block';
                    }
                    for (let icon of allIcons) {
                        icon.className = 'bi bi-chevron-up';
                    }
                    button.innerHTML = '<i class="bi bi-arrows-collapse me-1"></i>Collapse All';
                }
            }
            
            function toggleAllSteps(caseId) {
                const allStepBodies = document.querySelectorAll(`[id^="test-step-${caseId}-"]`);
                const allStepIcons = document.querySelectorAll(`[class^="toggle-step-icon-${caseId}-"] i`);
                
                // Check if any step is already expanded
                let anyExpanded = false;
                for (let body of allStepBodies) {
                    if (body.style.display === 'block') {
                        anyExpanded = true;
                        break;
                    }
                }
                
                // Toggle state based on current state
                if (anyExpanded) {
                    // Collapse all
                    for (let body of allStepBodies) {
                        body.style.display = 'none';
                    }
                    for (let icon of allStepIcons) {
                        icon.className = 'bi bi-chevron-down';
                    }
                } else {
                    // Expand all
                    for (let body of allStepBodies) {
                        body.style.display = 'block';
                    }
                    for (let icon of allStepIcons) {
                        icon.className = 'bi bi-chevron-up';
                    }
                }
            }
            
            function filterTestCases() {
                const searchInput = document.getElementById('searchInput');
                const filter = searchInput.value.toLowerCase();
                const testCases = document.querySelectorAll('.test-case');
                
                for (let testCase of testCases) {
                    const title = testCase.querySelector('h5').textContent.toLowerCase();
                    if (title.includes(filter)) {
                        testCase.style.display = '';
                    } else {
                        testCase.style.display = 'none';
                    }
                }
            }
            
            function filterByStatus(status) {
                const testCases = document.querySelectorAll('.test-case');
                const filterButtons = document.querySelectorAll('.filter-btn');
                
                // Update active button
                for (let btn of filterButtons) {
                    btn.classList.remove('active');
                    if (btn.textContent.toLowerCase().includes(status)) {
                        btn.classList.add('active');
                    }
                }
                
                // Filter test cases
                for (let testCase of testCases) {
                    if (status === 'all') {
                        testCase.style.display = '';
                    } else if (testCase.getAttribute('data-status') === status) {
                        testCase.style.display = '';
                    } else {
                        testCase.style.display = 'none';
                    }
                }
            }
            
            function copyToClipboard(elementId) {
                const element = document.getElementById(elementId);
                const button = document.getElementById('btn-' + elementId);
                const text = element.textContent;
                
                navigator.clipboard.writeText(text).then(function() {
                    // Success feedback
                    const originalText = button.innerHTML;
                    button.innerHTML = '<i class="bi bi-check"></i> Copied!';
                    button.classList.add('copy-success');
                    
                    // Reset button after 2 seconds
                    setTimeout(function() {
                        button.innerHTML = originalText;
                        button.classList.remove('copy-success');
                    }, 2000);
                }).catch(function(err) {
                    console.error('Could not copy text: ', err);
                    alert('Failed to copy: ' + err);
                });
            }
        </script>
    </div>
</body>
</html>
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    if not IS_DOCKER: print(f"HTML report generated: {output_file}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python html_report_generator.py <jtl_file> [output_file]")
        sys.exit(1)
    
    jtl_file = sys.argv[1]
    extension = f"_{date_time}.html"
    
    if len(sys.argv) >= 3:
        output_file = f"{sys.argv[2]}{extension}"
    else:
        base_name = os.path.splitext(os.path.basename(jtl_file))[0]
        output_file = f"{base_name}_report{extension}"
    
    if not IS_DOCKER: print(f"Parsing JTL file: {jtl_file}")
    test_cases = parse_jtl_file(jtl_file)
    
    if not IS_DOCKER: print(f"Found {len(test_cases)} test cases")
    stats = calculate_statistics(test_cases)
    
    if not IS_DOCKER: print(f"Generating HTML report: {output_file}")
    generate_html_report(test_cases, stats, output_file)
    
    if IS_DOCKER:
        result_test = "no_record" if stats['total'] == 0 else "yes" if stats['failed'] > 0 else "no"
        print(result_test)
    else:
        print("Summary:")
        print(f"  Total Tests: {stats['total']}")
        print(f"  Passed Tests: {stats['passed']}")
        print(f"  Failed Tests: {stats['failed']}")
        print(f"  Pass Rate: {stats['pass_percentage']:.2f}%")
        print(f"  Total Test Duration: {format_time(stats['total_duration'])}")
        print(f"  Total Assertions: {stats['total_assertions']}")
        print(f"  Passed Assertions: {stats['passed_assertions']}")
        print(f"  Failed Assertions: {stats['failed_assertions']}")
        print(f"  Assertion Pass Rate: {stats['assertion_pass_percentage']:.2f}%")
        
if __name__ == "__main__":
    main()