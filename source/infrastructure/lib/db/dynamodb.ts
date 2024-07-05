/**********************************************************************************************************************
 *  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.                                                *
 *                                                                                                                    *
 *  Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance    *
 *  with the License. A copy of the License is located at                                                             *
 *                                                                                                                    *
 *      http://www.apache.org/licenses/LICENSE-2.0                                                                    *
 *                                                                                                                    *
 *  or in the 'license' file accompanying this file. This file is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES *
 *  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    *
 *  and limitations under the License.                                                                                *
 *********************************************************************************************************************/

import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import { Construct } from "constructs";
import { DynamoDBTable } from "../shared/table";

export class DynamoDBConstruct extends Construct {
  readonly sessionTable: dynamodb.Table;
  readonly botTable: dynamodb.Table;
  readonly messageTable: dynamodb.Table;
  // public promptTableName: string;
  // public indexTableName: string;
  // public modelTableName: string;
  // public intentionTableName: string;

  public readonly byUserIdIndex: string = "byUserId";
  public readonly bySessionIdIndex: string = "bySessionId";
  public readonly byTimestampIndex: string = "byTimestamp";
  public readonly byVersion: string = "byVersion";

  constructor(scope: Construct, id: string) {
    super(scope, id);

    const sessionIdAttr = {
      name: "sessionId",
      type: dynamodb.AttributeType.STRING,
    }
    const userIdAttr = {
      name: "userId",
      type: dynamodb.AttributeType.STRING,
    }
    const botIdAttr = {
      name: "botId",
      type: dynamodb.AttributeType.STRING,
    }

    const versionAttr = {
      name: "version",
      type: dynamodb.AttributeType.STRING,
    }

    const messageIdAttr = {
      name: "messageId",
      type: dynamodb.AttributeType.STRING,
    }
    const timestampAttr = {
      name: "createTimestamp",
      type: dynamodb.AttributeType.STRING,
    }


    this.sessionTable = new DynamoDBTable(this, "SessionTable", sessionIdAttr, userIdAttr).table;
    this.sessionTable.addGlobalSecondaryIndex({
      indexName: this.byTimestampIndex,
      partitionKey: userIdAttr,
      sortKey: timestampAttr,
      projectionType: dynamodb.ProjectionType.ALL,
    });

    this.messageTable = new DynamoDBTable(this, "MessageTable", messageIdAttr, sessionIdAttr).table;
    this.messageTable.addGlobalSecondaryIndex({
      indexName: this.bySessionIdIndex,
      partitionKey: { name: "sessionId", type: dynamodb.AttributeType.STRING },
    });

    this.botTable = new DynamoDBTable(this, "BotTable", botIdAttr, versionAttr).table;
    this.botTable.addGlobalSecondaryIndex({
      indexName: this.byVersion,
      partitionKey: versionAttr,
      sortKey: botIdAttr,
      projectionType: dynamodb.ProjectionType.ALL,
    });

  }
}
