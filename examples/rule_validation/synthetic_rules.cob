      *> SYNTHETIC REFERENCE FRAGMENTS, NOT A DEPLOYABLE PROGRAM.
      *> These invented demonstration rules have no customer/business origin.
      *> Interface: amount is an integer 0..9999; name is ASCII, length 0..40.
      *> The adapter supplies DEMO-NAME-LENGTH before right-padding the input
      *> into DEMO-RAW-NAME. Output strings retain all 20 character positions.
      *> DECLARATIONS (reference types, not a complete compilation unit):
       01 DEMO-AMOUNT           PIC 9(4).
       01 DEMO-ELIGIBLE         PIC X.
       01 DEMO-NAME-LENGTH      PIC 9(2).
       01 DEMO-RAW-NAME         PIC X(40).
       01 DEMO-DISPLAY-NAME     PIC X(20).
       01 DEMO-TRUNCATED        PIC X.

      *> R-ELIGIBILITY: positive means eligibility is true; negative false.
           IF DEMO-AMOUNT >= 100
               MOVE 'Y' TO DEMO-ELIGIBLE
           ELSE
               MOVE 'N' TO DEMO-ELIGIBLE
           END-IF

      *> R-NAME-FORMAT: positive means input fits; negative means truncation.
      *> Alphanumeric MOVE left-aligns, pads with spaces, or truncates right.
           MOVE DEMO-RAW-NAME TO DEMO-DISPLAY-NAME
           IF DEMO-NAME-LENGTH > 20
               MOVE 'Y' TO DEMO-TRUNCATED
           ELSE
               MOVE 'N' TO DEMO-TRUNCATED
           END-IF
